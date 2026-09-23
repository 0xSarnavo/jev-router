#!/usr/bin/env python3
"""jev: let Jev pick the agent CLI, model, effort and MCP servers for a prompt, then start it.

  jev "add a pricing page"            show the picks, choose one, start it
  jev --use codex "..."               fix the CLI, Jev picks the rest
  jev --yes "..."                     take the recommendation without asking
  jev --all-mcp "..."                 keep every MCP server
  jev --dry "..."                     print the command instead of running it
"""
import os
import shlex
import shutil
import sys
from pathlib import Path

HERE = Path(os.path.realpath(__file__)).parent
sys.path.insert(0, str(HERE))
import jev  # noqa: E402
import mcps  # noqa: E402
import models  # noqa: E402
from router import STATE_DIR, load_config  # noqa: E402

HARNESSES = ("claude", "codex", "opencode")


def command(h, model, effort, prompt, mcp_args):
    if h == "claude":
        return ["claude", "--model", model, "--effort", effort, *mcp_args, prompt]
    if h == "codex":
        return ["codex", "-m", model, "-c", f'model_reasoning_effort="{effort}"', *mcp_args, prompt]
    return ["opencode", "-m", model, "--prompt", prompt]


def main(argv):
    flags = {a for a in argv if a in ("--yes", "--all-mcp", "--dry")}
    rest = [a for a in argv if a not in flags]
    use = None
    if rest[:1] == ["--use"]:
        use, rest = rest[1], rest[2:]
    prompt = " ".join(rest).strip()
    if not prompt:
        sys.exit(__doc__)
    cfg = load_config()
    installed = [h for h in HARNESSES if shutil.which(h)]
    if use and use not in installed:
        sys.exit(f"{use} is not installed")
    cwd = os.getcwd()
    servers = {h: mcps.servers(h, cwd) for h in installed}
    names = sorted({n for s in servers.values() for n in s})
    ctx = {"mcp_names": names}
    questions = {**models.questions(cfg["models"], ctx), **mcps.questions(cfg["mcp"], ctx)}
    notes = {h: cfg["launcher"]["notes"][h] for h in installed}
    if not use and len(installed) > 1:
        questions["launch:harness"] = {
            "type": "choice", "criteria": notes,
            "instructions": "Which coding agent is the best fit for the request in `prompt`, "
                            "weighing quality first and cost second?"}
    state = {"prompt": prompt, "project": Path(cwd).name}
    try:
        answers, meta = jev.evaluate(jev.load_key(cfg.get("env_file")), state, questions,
                                     cfg["model"], cfg["timeout_s"])
    except jev.JevError as e:
        sys.exit(f"jev: {e}")
    tier, score = models.tier(cfg["models"], answers)
    first = use or (answers["launch:harness"]["choice"] if "launch:harness" in answers else installed[0])
    order = [first] + [h for h in installed if h != first and not use]
    need = {n for n in names if f"mcp:{n}" not in answers
            or answers[f"mcp:{n}"]["noul"] > cfg["mcp"]["skip_threshold"]}
    print(f"Jev: {tier} task, effort {score}/4 ({meta['latency_ms']} ms).")
    options = []
    for h in order:
        model, effort = models.pick(cfg["models"], h, tier)
        keep = list(servers[h]) if "--all-mcp" in flags else [n for n in servers[h] if n in need]
        drop = [n for n in servers[h] if n not in keep]
        options.append((h, model, effort, keep, drop))
        tag = " (recommended)" if len(options) == 1 else ""
        mcp_note = f"MCP: {', '.join(keep) or 'none'}" + (f", drops {', '.join(drop)}" if drop else "")
        print(f"  {len(options)}. {h}: {models.label(model, effort)}{tag}. {mcp_note}")
    choice = 1
    if "--yes" not in flags and len(options) > 1:
        raw = input(f"Pick 1-{len(options)} [1], or q to quit: ").strip().lower()
        if raw == "q":
            return
        choice = int(raw) if raw.isdigit() and 1 <= int(raw) <= len(options) else 1
    h, model, effort, keep, _ = options[choice - 1]
    mcp_args, env = mcps.launch_config(h, keep, servers[h], STATE_DIR / "launch")
    cmd = command(h, model, effort, prompt, mcp_args)
    if "--dry" in flags:
        print(" ".join(shlex.quote(c) for c in cmd))
        return
    os.execvpe(cmd[0], cmd, {**os.environ, **env})


if __name__ == "__main__":
    main(sys.argv[1:])
