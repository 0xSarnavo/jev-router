#!/usr/bin/env python3
"""Claude Code hook: route each prompt to skills and tools with Jev.

  router.py session-start   SessionStart hook
  router.py prompt          UserPromptSubmit hook
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
import catalog  # noqa: E402
import jev  # noqa: E402

STATE_DIR = Path(os.environ.get("JEV_ROUTER_STATE", Path.home() / ".cache" / "jev-router"))
MODES = ("all", "smart", "ask", "off")
CMD_RE = re.compile(r"^\s*jev\s+(?:mode\s+)?(all|smart|ask|off|status)\s*$", re.I)


def load_config():
    cfg = json.loads((HERE / "config.json").read_text())
    local = HERE / "config.local.json"
    if local.exists():
        cfg.update(json.loads(local.read_text()))
    return cfg


def _session_file(sid):
    safe = re.sub(r"[^A-Za-z0-9_-]", "", sid or "default")[:80] or "default"
    return STATE_DIR / "sessions" / f"{safe}.json"


def load_session(sid, cfg):
    try:
        return json.loads(_session_file(sid).read_text())
    except (OSError, ValueError):
        return {"mode": cfg["default_mode"], "loaded": [], "fallback_shown": False}


def save_session(sid, s):
    p = _session_file(sid)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(s))


def log(entry):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    entry["ts"] = round(time.time())
    with open(STATE_DIR / "log.jsonl", "a") as f:
        f.write(json.dumps(entry) + "\n")


def skill_body(path):
    text = Path(path).read_text(errors="ignore")
    return re.sub(r"\A---\s*\n.*?\n---\s*\n", "", text, count=1, flags=re.S).strip()


def should_route(prompt, mode, cfg):
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


def build_questions(cfg, cat):
    skip = set(cfg["always_on"]) | set(cfg["gated_skills"]) | set(cfg["never_route"])
    options = {s["name"]: s["desc"] or None for s in cat["skills"] if s["name"] not in skip}
    options["none"] = "No specialised skill fits. The assistant can answer or do this directly."
    q = {
        "skill": {
            "type": "choice",
            "instructions": "Which specialised skill, if any, clearly matches the request in "
                            "`prompt`? Choose none unless one directly fits the task.",
            "criteria": options,
        }
    }
    for name, question in cfg["gated_skills"].items():
        q[f"gate:{name}"] = {"type": "noul", "instructions": question}
    for group, desc in cfg["tool_groups"].items():
        q[f"tool:{group}"] = {
            "type": "noul",
            "instructions": f"Will handling the request in `prompt` need {desc}?",
        }
    return q


def decide(answers, cfg, loaded):
    t = cfg["thresholds"]
    picks = [name for name in cfg["gated_skills"]
             if answers[f"gate:{name}"]["noul"] >= t["gate"]]
    sk = answers["skill"]
    if sk["choice"] != "none" and sk["probabilities"].get(sk["choice"], 0) >= t["skill"]:
        picks.append(sk["choice"])
    new = [p for p in picks if p not in loaded]
    use, skip = [], []
    for group in cfg["tool_groups"]:
        p = answers[f"tool:{group}"]["noul"]
        if p >= t["tool_use"]:
            use.append(group)
        elif p <= t["tool_skip"]:
            skip.append(group)
    return new, [p for p in picks if p in loaded], use, skip


def render(new, active, use, skip, paths):
    lines = []
    for name in new:
        lines.append(f"Load skill `{name}`: read {paths[name]} and follow it for this task.")
    if active:
        lines.append("Already active this session: " + ", ".join(active) + ".")
    if use:
        lines.append("Tools likely needed: " + ", ".join(use) + ".")
    if skip:
        lines.append("Tools not needed, skip them: " + ", ".join(skip) + ".")
    if not new and not active:
        lines.append("No specialised skill needed.")
    return "[jev-router] " + " ".join(lines)


def emit(event, context):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": event,
                                             "additionalContext": context}}))


def on_session_start(data, cfg):
    cat = catalog.load(STATE_DIR)
    sid = data.get("session_id")
    s = load_session(sid, cfg)
    s["loaded"], s["fallback_shown"] = [], False
    save_session(sid, s)
    emit("SessionStart", f"[jev-router] Routing mode: {s['mode']}. Skills load on demand; "
         "follow [jev-router] notes on each prompt. The user switches mode with "
         "`jev all|smart|ask|off`.")


def on_always_on(name, cfg):
    """One hook per skill: Claude Code truncates a single large hook output."""
    path = {x["name"]: x["path"] for x in catalog.load(STATE_DIR)["skills"]}.get(name)
    if path and name in cfg["always_on"]:
        emit("SessionStart", f"## Always-on skill: {name}\n\n{skill_body(path)}")


def on_prompt(data, cfg):
    prompt = data.get("prompt") or ""
    sid = data.get("session_id")
    s = load_session(sid, cfg)
    cmd = CMD_RE.match(prompt)
    if cmd:
        word = cmd.group(1).lower()
        if word != "status":
            s["mode"] = word
            save_session(sid, s)
        msg = (f"jev-router mode: {s['mode']}. Active skills: "
               f"{', '.join(s['loaded']) or 'none'}.")
        print(json.dumps({"decision": "block", "reason": msg}))
        return
    if not should_route(prompt, s["mode"], cfg):
        return
    cat = catalog.load(STATE_DIR)
    paths = {x["name"]: x["path"] for x in cat["skills"]}
    state = {"prompt": prompt, "project": Path(data.get("cwd") or ".").name}
    digest = hashlib.sha256(prompt.encode()).hexdigest()[:12]
    try:
        key = jev.load_key(cfg.get("env_file"))
        answers, meta = jev.evaluate(key, state, build_questions(cfg, cat),
                                     cfg["model"], cfg["timeout_s"])
    except jev.JevError as e:
        log({"event": "error", "prompt_sha": digest, "error": str(e)})
        if not s["fallback_shown"]:
            s["fallback_shown"] = True
            save_session(sid, s)
            emit("UserPromptSubmit", "[jev-router] Router unavailable. If a specialised "
                 f"skill could help, pick one from {STATE_DIR / 'catalog.md'}.")
        return
    new, active, use, skip = decide(answers, cfg, s["loaded"])
    new = [n for n in new if n in paths]
    s["loaded"] += new
    save_session(sid, s)
    log({"event": "route", "prompt_sha": digest, "mode": s["mode"], "new": new,
         "active": active, "use": use, "skip": skip,
         "skill_choice": answers["skill"]["choice"],
         "skill_p": round(answers["skill"]["probabilities"].get(answers["skill"]["choice"], 0), 3),
         **meta})
    emit("UserPromptSubmit", render(new, active, use, skip, paths))


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


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # a router bug must never block the user's prompt
        try:
            log({"event": "crash", "error": f"{type(e).__name__}: {e}"})
        except Exception:
            pass
    sys.exit(0)
