#!/usr/bin/env python3
"""Claude Code hook entry point. Runs the enabled routers in one Jev request.

  router.py session-start      SessionStart hook
  router.py always-on <skill>  SessionStart hook, one per always-on skill
  router.py prompt             UserPromptSubmit hook
"""
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import context  # noqa: E402
import jev  # noqa: E402
import mcps  # noqa: E402
import models  # noqa: E402
import skills  # noqa: E402
import tools  # noqa: E402

STATE_DIR = Path(os.environ.get("JEV_ROUTER_STATE", Path.home() / ".cache" / "jev-router"))
ROUTERS = {"skills": skills, "tools": tools, "mcp": mcps, "models": models, "context": context}
NOT_USER = ("<task-notification", "[SYSTEM NOTIFICATION", "<system-reminder", "<local-command")
MODE_RE = re.compile(r"^\s*jev\s+(?:mode\s+)?(all|smart|ask|off|status)\s*$", re.I)
TOGGLE_RE = re.compile(r"^\s*jev\s+(skills|tools|mcp|models|context)\s+(on|off)\s*$", re.I)
BACKEND_RE = re.compile(r"^\s*jev\s+backend\s+(jev|laya|auto)\s*$", re.I)
MODEL_RE = re.compile(r"^\s*jev\s+model\s+(suggest|ask|auto|off)\s*$", re.I)


def load_config():
    cfg = json.loads((HERE / "config.json").read_text())
    local = HERE / "config.local.json"
    if local.exists():
        for k, v in json.loads(local.read_text()).items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    return cfg


def _session_file(sid):
    safe = re.sub(r"[^A-Za-z0-9_-]", "", sid or "default")[:80] or "default"
    return STATE_DIR / "sessions" / f"{safe}.json"


def load_session(sid, cfg):
    s = {"mode": cfg["default_mode"], "off": [], "loaded": [], "fallback_shown": False}
    try:
        s.update(json.loads(_session_file(sid).read_text()))
    except (OSError, ValueError):
        pass
    return s


def save_session(sid, s):
    p = _session_file(sid)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(s))


def log(entry):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    entry["ts"] = round(time.time())
    with open(STATE_DIR / "log.jsonl", "a") as f:
        f.write(json.dumps(entry) + "\n")


def enabled(cfg, s):
    return [n for n in ROUTERS if cfg[n]["enabled"] and n not in s["off"]]


def should_route(prompt, mode, cfg):
    if prompt.lstrip().startswith(NOT_USER):
        return False
    if mode == "off":
        return False
    if mode == "ask":
        return prompt.lstrip().lower().startswith(cfg["ask_prefix"])
    if prompt.lstrip().startswith("/"):
        return False
    if mode == "smart":
        if len(prompt.split()) < cfg["smart"]["min_words"]:
            return False
        if re.search(cfg["smart"]["skip_regex"], prompt, re.I):
            return False
    return True


def emit(event, context):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": event,
                                             "additionalContext": context}}))


def block(msg):
    print(json.dumps({"decision": "block", "reason": msg}))


def status(cfg, s):
    return (f"jev-router mode: {s['mode']}. Routers on: {', '.join(enabled(cfg, s)) or 'none'}. "
            f"Model mode: {s.get('model_mode', cfg['models']['mode'])}. "
            f"Backend: {s.get('backend', cfg['backend'])}. "
            f"Skills loaded: {', '.join(s['loaded']) or 'none'}.")


def on_session_start(data, cfg):
    sid = data.get("session_id")
    s = load_session(sid, cfg)
    s["loaded"], s["fallback_shown"] = [], False
    for k in ("model_asked", "handed", "memory_shown"):
        s.pop(k, None)
    save_session(sid, s)
    if cfg["skills"]["enabled"]:
        skills.load_catalog(STATE_DIR)
    emit("SessionStart", f"[jev-router] Mode: {s['mode']}. Routers: {', '.join(enabled(cfg, s))}. "
         "Follow [jev-router] notes on each prompt. The user controls routing with "
         "`jev all|smart|ask|off` and `jev skills|tools on|off`. "
         "When a reply changes or advances work, end it with one line: "
         "`Handoff: <what is being done> | next: <next step>`, under 25 words. "
         "Another agent may continue from that line.")


def on_always_on(name, cfg):
    """One hook per skill: Claude Code truncates a single large hook output."""
    path = skills.paths(STATE_DIR).get(name)
    if path and name in cfg["skills"]["always_on"]:
        emit("SessionStart", f"## Always-on skill: {name}\n\n{skills.body(path)}")


def on_prompt(data, cfg):
    prompt = data.get("prompt") or ""
    sid = data.get("session_id")
    s = load_session(sid, cfg)
    if m := MODE_RE.match(prompt):
        if m.group(1).lower() != "status":
            s["mode"] = m.group(1).lower()
            save_session(sid, s)
        return block(status(cfg, s))
    if m := TOGGLE_RE.match(prompt):
        name, on = m.group(1).lower(), m.group(2).lower() == "on"
        s["off"] = [n for n in s["off"] if n != name] + ([] if on else [name])
        save_session(sid, s)
        return block(status(cfg, s))
    if m := BACKEND_RE.match(prompt):
        s["backend"] = m.group(1).lower()
        save_session(sid, s)
        return block(status(cfg, s))
    if m := MODEL_RE.match(prompt):
        s["model_mode"] = m.group(1).lower()
        save_session(sid, s)
        return block(status(cfg, s))
    if not prompt.lstrip().startswith(NOT_USER):
        s["pending_prompt"] = prompt
        save_session(sid, s)
    names = enabled(cfg, s)
    if not names or not should_route(prompt, s["mode"], cfg):
        return
    harness = models.harness_of(data)
    ctx = {"state_dir": STATE_DIR, "data": data, "prompt": prompt, "harness": harness,
           "mcp_names": list(mcps.servers(harness, data.get("cwd"))), "session": s}
    questions = {}
    for n in names:
        questions.update(ROUTERS[n].questions(cfg[n], ctx))
    state = {"prompt": prompt, "project": Path(data.get("cwd") or ".").name}
    digest = hashlib.sha256(prompt.encode()).hexdigest()[:12]
    try:
        answers, meta = jev.ask(cfg, state, questions, s.get("backend"))
        ctx["backend"] = meta["backend"]
    except jev.JevError as e:
        log({"event": "error", "prompt_sha": digest, "error": str(e)})
        if "skills" in names and not s["fallback_shown"]:
            s["fallback_shown"] = True
            save_session(sid, s)
            emit("UserPromptSubmit", "[jev-router] Router unavailable. If a specialised "
                 f"skill could help, pick one from {STATE_DIR / 'catalog.md'}.")
        return
    lines, entry = [], {"event": "route", "prompt_sha": digest, "mode": s["mode"],
                        "harness": harness, **meta}
    for n in names:
        if not any(k in answers for k in ROUTERS[n].questions(cfg[n], ctx)):
            continue
        line, detail = ROUTERS[n].route(cfg[n], answers, s, ctx)
        if line:
            lines.append(line)
        entry[n] = detail
    save_session(sid, s)
    log(entry)
    if (entry.get("models") or {}).get("block"):
        return block(entry["models"]["block"])
    out = {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                  "additionalContext": "[jev-router] " + " ".join(lines)}} if lines else {}
    if harness == "opencode" and (entry.get("models") or {}).get("switch"):
        out["jevModel"] = entry["models"]["switch"]
    if out:
        print(json.dumps(out))


def on_stop(data, cfg):
    s = load_session(data.get("session_id"), cfg)
    if cfg["context"]["enabled"] and "context" not in s["off"]:
        context.capture(cfg["context"], data, s, models.harness_of(data), STATE_DIR)


def main():
    event = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        data = json.load(sys.stdin)
    except ValueError:
        data = {}
    cfg = load_config()
    if event == "session-start":
        on_session_start(data, cfg)
    elif event == "always-on" and len(sys.argv) > 2:
        on_always_on(sys.argv[2], cfg)
    elif event == "prompt":
        on_prompt(data, cfg)
    elif event == "stop":
        on_stop(data, cfg)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # a router bug must never block the user's prompt
        try:
            log({"event": "crash", "error": f"{type(e).__name__}: {e}"})
        except Exception:
            pass
    sys.exit(0)
