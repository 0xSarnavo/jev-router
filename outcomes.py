"""Outcome log for reinforcement learning: what the router advised versus what the agent did.

The Stop hook compares the router's last decision for the session with the tools, MCP servers
and skills the agent actually used in that turn. Rewards are derived from these rows later.
Rows hold prompt text, so they stay in ~/.cache/jev-router/outcomes.jsonl on this machine.
"""
import json
import re
import time
from pathlib import Path

GH_RE = re.compile(r"(^|[;&|(]\s*)gh\s")
MCP_RE = re.compile(r"^mcp__(?:plugin_[^_]+_)?([A-Za-z0-9-]+?)__")


def tool_calls_claude(path):
    """Tool calls in the last turn of a Claude Code transcript, as (name, input)."""
    calls = []
    for line in Path(path).read_text(errors="ignore").splitlines()[-400:]:
        try:
            d = json.loads(line)
        except ValueError:
            continue
        content = (d.get("message") or {}).get("content")
        if d.get("type") == "user" and not d.get("isMeta") and (
                isinstance(content, str) or any(isinstance(c, dict) and c.get("type") == "text" for c in content or [])):
            calls = []
        if d.get("type") == "assistant" and isinstance(content, list):
            calls += [(c.get("name", ""), c.get("input") or {}) for c in content
                      if isinstance(c, dict) and c.get("type") == "tool_use"]
    return calls


def tool_calls_codex(path):
    calls = []
    for line in Path(path).read_text(errors="ignore").splitlines()[-400:]:
        try:
            p = json.loads(line).get("payload") or {}
        except ValueError:
            continue
        if p.get("type") == "user_message":
            calls = []
        elif p.get("type") in ("function_call", "custom_tool_call", "mcp_tool_call"):
            calls.append((p.get("name") or p.get("tool") or "", {"arguments": p.get("arguments", "")}))
    return calls


def summarise(calls, match, skill_paths):
    used_groups, used_mcp, read_skills = set(), set(), set()
    for name, inp in calls:
        m = MCP_RE.match(name)
        if m:
            used_mcp.add(m.group(1).replace("_", "-"))
        for group, needles in match.items():
            if any(n in name for n in needles):
                used_groups.add(group)
        if name == "Bash" and GH_RE.search(str(inp.get("command", ""))):
            used_groups.add("github")
        if name == "Read" and inp.get("file_path") in skill_paths.values():
            read_skills.add(next(k for k, v in skill_paths.items() if v == inp["file_path"]))
        if name == "Skill" and inp.get("skill"):
            read_skills.add(inp["skill"])
    return used_groups, used_mcp, read_skills


def record(cfg, data, session, harness, skill_paths, state_dir):
    last = session.get("last_route")
    tp = data.get("transcript_path")
    if not last or not tp or not Path(tp).exists():
        return
    calls = (tool_calls_codex if harness == "codex" else tool_calls_claude)(tp)
    groups, mcp, skills = summarise(calls, cfg["match"], skill_paths)
    row = {"ts": int(time.time()), "harness": harness, "prompt": last["prompt"], "project": last["project"],
           "advised": {k: last[k] for k in ("skills", "tools_use", "tools_skip", "mcp_use", "mcp_skip")},
           "did": {"tools": sorted(groups), "mcp": sorted(mcp), "skills": sorted(skills), "calls": len(calls)},
           "answers": last["answers"]}
    p = Path(state_dir) / "outcomes.jsonl"
    with open(p, "a") as f:
        f.write(json.dumps(row) + "\n")
    session.pop("last_route", None)
