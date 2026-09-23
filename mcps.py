"""MCP router: which MCP servers a prompt needs, as a hint in-session and as config at launch."""
import json
import tomllib
from pathlib import Path

HOME = Path.home()


def claude_servers(cwd=None):
    """User and project servers from ~/.claude.json plus the project's .mcp.json, with definitions."""
    out = {}
    try:
        c = json.loads((HOME / ".claude.json").read_text())
    except (OSError, ValueError):
        c = {}
    out.update(c.get("mcpServers") or {})
    if cwd:
        out.update((c.get("projects") or {}).get(str(cwd), {}).get("mcpServers") or {})
        try:
            out.update(json.loads((Path(cwd) / ".mcp.json").read_text()).get("mcpServers") or {})
        except (OSError, ValueError):
            pass
    return out


def codex_servers():
    try:
        c = tomllib.loads((HOME / ".codex" / "config.toml").read_text())
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in (c.get("mcp_servers") or {}).items() if v.get("enabled", True)}


def opencode_servers():
    try:
        c = json.loads((HOME / ".config" / "opencode" / "opencode.json").read_text())
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in (c.get("mcp") or {}).items() if v.get("enabled", True)}


def servers(harness, cwd=None):
    return {"claude": lambda: claude_servers(cwd), "codex": codex_servers,
            "opencode": opencode_servers}[harness]()


def _desc(cfg, name):
    return cfg["describe"].get(name, f"the {name} MCP server")


def questions(cfg, ctx):
    names = ctx["mcp_names"]
    return {f"mcp:{n}": {"type": "noul",
                         "instructions": f"Will handling the request in `prompt` need {_desc(cfg, n)}?"}
            for n in names if n not in cfg["ignore"]}


def needed(cfg, answers, names):
    use = [n for n in names if f"mcp:{n}" in answers
           and answers[f"mcp:{n}"]["noul"] >= cfg["use_threshold"]]
    skip = [n for n in names if f"mcp:{n}" in answers
            and answers[f"mcp:{n}"]["noul"] <= cfg["skip_threshold"]]
    return use, skip


def route(cfg, answers, session, ctx):
    use, skip = needed(cfg, answers, ctx["mcp_names"])
    parts = []
    if use:
        parts.append("MCP servers likely needed: " + ", ".join(use) + ".")
    if skip:
        parts.append("MCP servers not needed, do not search or call their tools: " + ", ".join(skip) + ".")
    return " ".join(parts), {"use": use, "skip": skip}


def launch_config(harness, keep, all_servers, cache_dir):
    """Extra argv and env that start the harness with only the `keep` servers."""
    drop = [n for n in all_servers if n not in keep]
    if harness == "claude":
        cache_dir.mkdir(parents=True, exist_ok=True)
        path = cache_dir / "launch-mcp.json"
        path.touch(mode=0o600, exist_ok=True)
        path.write_text(json.dumps({"mcpServers": {n: all_servers[n] for n in keep}}))
        return ["--mcp-config", str(path), "--strict-mcp-config"], {}
    if harness == "codex":
        args = []
        for n in drop:
            args += ["-c", f"mcp_servers.{n}.enabled=false"]
        return args, {}
    return [], {"OPENCODE_CONFIG_CONTENT": json.dumps({"mcp": {n: {"enabled": False} for n in drop}})}
