#!/usr/bin/env python3
"""Wire jev-router into Claude Code, Codex and OpenCode, or undo it with --uninstall."""
import json
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import skills  # noqa: E402
from router import STATE_DIR, load_config  # noqa: E402

HOME = Path.home()
CLAUDE = HOME / ".claude" / "settings.json"
CODEX = HOME / ".codex" / "hooks.json"
OPENCODE = HOME / ".config" / "opencode" / "plugins" / "jev-router.js"
RECORD = STATE_DIR / "installed.json"
ROUTER = str(HERE / "router.py")
LAUNCHER = HERE / "launch.py"
LINK = HOME / ".local" / "bin" / "jev"


def hook(arg, timeout):
    return {"hooks": [{"type": "command", "command": f'"{sys.executable}" "{ROUTER}" {arg}',
                       "timeout": timeout}]}


def ours(entry):
    return any(ROUTER in h.get("command", "") for h in entry.get("hooks", []))


def backup(path):
    shutil.copy(path, path.with_name(f"{path.name}.bak-jev-router-{int(time.time())}"))


def set_hooks(path, wanted):
    """Replace our hook entries in a Claude-style hooks file, keeping everyone else's."""
    s = json.loads(path.read_text()) if path.exists() else {}
    if path.exists():
        backup(path)
    hooks = s.setdefault("hooks", {})
    for event in list(hooks):
        hooks[event] = [e for e in hooks[event] if not ours(e)]
        if not hooks[event]:
            del hooks[event]
    for event, entries in wanted.items():
        hooks.setdefault(event, []).extend(entries)
    return s


def install(cfg, rec):
    timeout = cfg["timeout_s"] + cfg["laya"]["timeout_s"] + 4
    claude = {"SessionStart": [hook("session-start", 10)] +
              [hook(f"always-on {n}", 10) for n in cfg["skills"]["always_on"]],
              "UserPromptSubmit": [hook("prompt", timeout)], "Stop": [hook("stop", 10)]}
    s = set_hooks(CLAUDE, claude)
    overrides = s.setdefault("skillOverrides", {})
    for sk in skills.build_catalog(STATE_DIR)["skills"]:
        if sk["name"] not in overrides and sk["name"] not in cfg["skills"]["never_route"]:
            overrides[sk["name"]] = "user-invocable-only"
            rec["added_overrides"].append(sk["name"])
    CLAUDE.write_text(json.dumps(s, indent=2) + "\n")
    print("claude: hooks and skill overrides set")
    if shutil.which("codex"):
        codex = {k: v for k, v in claude.items() if k != "SessionStart"}
        codex["SessionStart"] = [hook("session-start", 10)]
        CODEX.write_text(json.dumps(set_hooks(CODEX, codex), indent=2) + "\n")
        print("codex: hooks set. Trust them once in Codex: it shows 'Hooks need review' at start")
    if shutil.which("opencode"):
        OPENCODE.parent.mkdir(parents=True, exist_ok=True)
        js = (HERE / "opencode" / "jev-router.js").read_text()
        OPENCODE.write_text(js.replace("__PYTHON__", sys.executable).replace("__ROUTER__", ROUTER))
        print(f"opencode: plugin written to {OPENCODE}")
    LINK.parent.mkdir(parents=True, exist_ok=True)
    if not LINK.exists():
        LINK.symlink_to(LAUNCHER)
    elif not (LINK.is_symlink() and LINK.resolve() == LAUNCHER):
        print(f"{LINK} exists and is not ours; launcher not linked")


def uninstall(rec):
    s = set_hooks(CLAUDE, {})
    for name in rec["added_overrides"]:
        s.get("skillOverrides", {}).pop(name, None)
    CLAUDE.write_text(json.dumps(s, indent=2) + "\n")
    if CODEX.exists():
        CODEX.write_text(json.dumps(set_hooks(CODEX, {}), indent=2) + "\n")
    if OPENCODE.exists() and ROUTER in OPENCODE.read_text():
        OPENCODE.unlink()
    if LINK.is_symlink() and LINK.resolve() == LAUNCHER:
        LINK.unlink()
    RECORD.unlink(missing_ok=True)
    print("uninstalled from claude, codex and opencode")


def main():
    rec = json.loads(RECORD.read_text()) if RECORD.exists() else {"added_overrides": []}
    if "--uninstall" in sys.argv:
        return uninstall(rec)
    install(load_config(), rec)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    RECORD.write_text(json.dumps(rec, indent=1))


if __name__ == "__main__":
    main()
