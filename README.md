# jev-router

A per-prompt skill and tool router for [Claude Code](https://claude.com/claude-code), powered by
[Jev](https://docs.typesafe.ai), TypeSafe's System One model.

Claude Code lists every skill description at startup. With a hundred or more skills that is a lot
of context spent before you type. jev-router hides the skills and loads them on demand:

1. **Session start.** A hook injects the skills you always want (default: `i-have-adhd`, `caveman`).
2. **Each prompt.** A hook sends the prompt to Jev in one request with typed questions:
   - yes/no gates for context skills: `ponytail` when code will change, `no-ai-slop` when writing
     prose, `potpie-cli` when the answer needs recorded project history;
   - one choice over every other skill in `~/.claude/skills`, including `none`;
   - one yes/no per tool group (web, browser, railway, figma, github, subagents).
3. **Advice, not control.** The hook adds one `[jev-router]` line telling Claude which skill files
   to read and which tool groups to skip. Nothing is blocked. Skills are loaded once per session.

If Jev is unreachable, Claude is pointed at a local markdown index of the skills instead.

Measured on six sample prompts: about 7k Jev tokens and 0.6 to 0.75 s per prompt.

## Modes

Type these as a prompt. They are handled by the hook and never reach Claude.

| Prompt | Effect for this session |
| --- | --- |
| `jev all` | Route every prompt except slash commands |
| `jev smart` | Default. Also skip short or trivial prompts like `ok`, `continue` |
| `jev ask` | Route only prompts that start with `jev:` |
| `jev off` | No routing |
| `jev status` | Show mode and skills loaded so far |

## Privacy

Routed prompt text and the project folder name are sent to the TypeSafe API. Use `jev ask` or
`jev off` in sessions where that is not acceptable. The local log at
`~/.cache/jev-router/log.jsonl` stores decisions and a prompt hash, never prompt text.

## Install

Needs Python 3.9+ (stdlib only) and `TYPESAFE_API_KEY` in the environment Claude Code runs in.

```sh
python3 install.py          # add hooks, hide routed skills from the startup list
python3 install.py --uninstall
```

The installer backs up `~/.claude/settings.json` and records which skill overrides it added, so
uninstall removes only those. Rerun it after changing `always_on`.

Hidden skills still work as slash commands, for example `/ponytail`.

## Configure

Edit `config.json`, or put overrides in `config.local.json` (git-ignored). Thresholds are the
minimum probability to load a gated skill (`gate`), pick a skill (`skill`), and mark a tool
group needed (`tool_use`) or skippable (`tool_skip`). Set `env_file` to read the key from a
`.env` file when the environment lacks it.

## Test

```sh
python3 -m unittest discover -s tests
```
