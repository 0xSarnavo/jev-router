#!/usr/bin/env python3
"""Wire jev-router into ~/.claude/settings.json, or undo it with --uninstall."""
import json
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import skills  # noqa: E402
from router import STATE_DIR, load_config  # noqa: E402

SETTINGS = Path.home() / ".claude" / "settings.json"
RECORD = STATE_DIR / "installed.json"
ROUTER = str(HERE / "router.py")
LAUNCHER = HERE / "launch.py"
LINK = Path.home() / ".local" / "bin" / "jev"


def hook(arg, timeout):
    return {"hooks": [{"type": "command", "command": f'"{sys.executable}" "{ROUTER}" {arg}',
                       "timeout": timeout}]}


def ours(entry):
    return any(ROUTER in h.get("command", "") for h in entry.get("hooks", []))


def main():
    uninstall = "--uninstall" in sys.argv
    s = json.loads(SETTINGS.read_text())
    backup = SETTINGS.with_name(f"settings.json.bak-jev-router-{int(time.time())}")
    shutil.copy(SETTINGS, backup)
    hooks = s.setdefault("hooks", {})
    for event in ("SessionStart", "UserPromptSubmit"):
        hooks[event] = [e for e in hooks.get(event, []) if not ours(e)]
    overrides = s.setdefault("skillOverrides", {})
    if uninstall:
        rec = json.loads(RECORD.read_text()) if RECORD.exists() else {"added_overrides": []}
        for name in rec["added_overrides"]:
            overrides.pop(name, None)
        RECORD.unlink(missing_ok=True)
        if LINK.is_symlink() and LINK.resolve() == LAUNCHER:
            LINK.unlink()
        for event in ("SessionStart", "UserPromptSubmit"):
            if not hooks[event]:
                del hooks[event]
    else:
        cfg = load_config()
        cat = skills.build_catalog(STATE_DIR)
        hooks["SessionStart"].append(hook("session-start", 10))
        for name in cfg["skills"]["always_on"]:
            hooks["SessionStart"].append(hook(f"always-on {name}", 10))
        hooks["UserPromptSubmit"].append(hook("prompt", cfg["timeout_s"] + 4))
        rec = json.loads(RECORD.read_text()) if RECORD.exists() else {"added_overrides": []}
        for sk in cat["skills"]:
            if sk["name"] not in overrides and sk["name"] not in cfg["skills"]["never_route"]:
                overrides[sk["name"]] = "user-invocable-only"
                rec["added_overrides"].append(sk["name"])
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        RECORD.write_text(json.dumps(rec, indent=1))
        LINK.parent.mkdir(parents=True, exist_ok=True)
        if not LINK.exists():
            LINK.symlink_to(LAUNCHER)
        elif not (LINK.is_symlink() and LINK.resolve() == LAUNCHER):
            print(f"{LINK} exists and is not ours; launcher not linked")
    SETTINGS.write_text(json.dumps(s, indent=2) + "\n")
    print(("uninstalled" if uninstall else "installed") + f"; backup at {backup}")


if __name__ == "__main__":
    main()
