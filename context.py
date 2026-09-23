"""Context router: hand the relevant recent turns to whichever CLI takes the next prompt."""
import hashlib
import json
import re
import subprocess
import time
from pathlib import Path

HANDOFF_RE = re.compile(r"^\s*\**Handoff:?\**:?\s*(.+)$", re.I | re.M)
GRAPHIFY = Path.home() / ".cache" / "jev-router" / "graphify-venv" / "bin" / "graphify"


def potpie_pot(root):
    """Pot linked to this repo, read from Potpie's own file. `potpie pot linked` takes ~2 s."""
    try:
        data = json.loads((Path.home() / ".potpie" / "pots.json").read_text())
    except (OSError, ValueError):
        return None
    for pot_id, sources in (data.get("sources") or {}).items():
        if any(root == s.get("location") or root.startswith(s.get("location", "") + "/")
               for s in sources if s.get("location")):
            return (data.get("pots") or {}).get(pot_id, {}).get("name", pot_id)
    return None


def memory_pointers(root):
    """Paths and one-line commands only. The agent reads them if it needs them."""
    r, out = Path(root), []
    for rel in (".planning/.continue-here.md", ".planning/HANDOFF.json", ".planning/STATE.md"):
        if (r / rel).exists():
            out.append(f"GSD handoff: {rel}")
            break
    graph = next((r / g for g in (".planning/graphs/graph.json", "graphify-out/graph.json")
                  if (r / g).exists()), None)
    if graph:
        cmd = GRAPHIFY if GRAPHIFY.exists() else "graphify"
        out.append(f"Code graph: `{cmd} explain <symbol> --graph {graph.relative_to(r)}` for "
                   "callers and callees. Never dump the whole graph")
    pot = potpie_pot(root)
    if pot:
        out.append(f"Potpie pot `{pot}`: `potpie --json graph search-entities \"<question>\" "
                   "--limit 3` for past decisions")
    return out


def repo_root(cwd):
    try:
        out = subprocess.run(["git", "-C", cwd, "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=3)
        if out.returncode == 0:
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return str(cwd)


def _log_path(state_dir, root):
    return Path(state_dir) / "handoff" / (hashlib.sha256(root.encode()).hexdigest()[:16] + ".jsonl")


def changed_files(root, limit=15):
    try:
        out = subprocess.run(["git", "-C", root, "status", "--porcelain"],
                             capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [line[3:] for line in out.splitlines()][:limit]


def capture(cfg, data, session, harness, state_dir):
    """Stop hook: append one compact entry for this turn."""
    cwd = data.get("cwd") or "."
    root = repo_root(cwd)
    reply = data.get("last_assistant_message") or ""
    m = HANDOFF_RE.findall(reply)
    entry = {"id": f"{data.get('session_id', '')[:8]}-{int(time.time())}", "ts": int(time.time()),
             "harness": harness, "session": data.get("session_id"), "model": data.get("model"),
             "prompt": (session.get("pending_prompt") or "")[:400],
             "handoff": m[-1].strip()[:300] if m else "",
             "reply": HANDOFF_RE.sub("", reply).strip()[:cfg["reply_chars"]],
             "files": changed_files(root), "transcript": data.get("transcript_path")}
    if not entry["prompt"] and not reply:
        return
    p = _log_path(state_dir, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = (p.read_text().splitlines() if p.exists() else [])[-(cfg["keep"] - 1):]
    p.write_text("\n".join(lines + [json.dumps(entry)]) + "\n")


def candidates(cfg, ctx, session):
    """Recent turns from other sessions in this repo, not yet handed to this session."""
    root = repo_root(ctx["data"].get("cwd") or ".")
    p = _log_path(ctx["state_dir"], root)
    if not p.exists():
        return root, []
    cutoff = time.time() - cfg["max_age_h"] * 3600
    sid, seen = ctx["data"].get("session_id"), set(session.get("handed", []))
    out = []
    for line in p.read_text().splitlines()[-cfg["scan"]:]:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e["session"] != sid and e["id"] not in seen and e["ts"] >= cutoff:
            out.append(e)
    return root, out


def questions(cfg, ctx):
    _, cands = candidates(cfg, ctx, ctx["session"])
    return {f"ctx:{e['id']}": {
        "type": "noul",
        "instructions": {
            "earlier_turn": {"asked": e["prompt"], "handoff": e["handoff"], "reply": e["reply"][:300],
                             "files": e["files"][:8]},
            "question": "Is `earlier_turn` work that the request in `prompt` continues, depends "
                        "on or refers to?"}}
        for e in cands}


def _age(ts):
    m = int((time.time() - ts) // 60)
    return f"{m} min ago" if m < 90 else f"{m // 60} h ago"


def route(cfg, answers, session, ctx):
    root, cands = candidates(cfg, ctx, session)
    picked = [e for e in cands if answers.get(f"ctx:{e['id']}", {}).get("noul", 0) >= cfg["threshold"]]
    if not picked:
        return "", {"picked": 0}
    lines, used = [], 0
    for e in reversed(picked):
        reply = " ".join(e["reply"].split())
        item = (f"- {e['harness']}, {_age(e['ts'])}: asked \"{e['prompt'][:160]}\"."
                + (f" Handoff: {e['handoff']}." if e["handoff"] else "")
                + (f" Reply: {reply}" if reply else "")
                + (f" Files changed: {', '.join(e['files'][:6])}." if e["files"] else ""))
        if used + len(item) > cfg["budget_chars"]:
            break
        lines.append(item)
        used += len(item)
    session["handed"] = session.get("handed", []) + [e["id"] for e in picked]
    last = picked[-1]
    parts = ["Handover from earlier work in this repo, newest first:", *lines]
    if last.get("transcript"):
        parts.append(f"Full earlier transcript, search it only if you need more: {last['transcript']}")
    if not session.get("memory_shown"):
        mem = memory_pointers(root)
        if mem:
            parts.append("Also available: " + "; ".join(mem) + ".")
            session["memory_shown"] = True
    return "\n".join(parts), {"picked": len(picked), "offered": len(cands)}
