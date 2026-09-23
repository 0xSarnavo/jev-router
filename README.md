# jev-router

Per-prompt routing for coding agents, powered by [Jev](https://docs.typesafe.ai), TypeSafe's
System One model. Jev returns typed answers and probabilities in well under a second, which makes
it cheap enough to run before every prompt.

There are three routers. Each has its own config section, can be switched off on its own, and
shares one Jev request per prompt with the others.

| Router | What it decides | Status |
| --- | --- | --- |
| [Skill router](docs/skill-router.md) | Which skill files to load for this prompt, if any | Working, Claude Code |
| [Tool router](docs/tool-router.md) | Which tool groups the prompt needs and which to skip | Working, Claude Code |
| [Model router](docs/model-router.md) | Which model, and which agent CLI, should handle the prompt | Planned |

Claude Code lists every skill description at startup. With 140 skills that is thousands of
tokens spent before the first prompt. The skill router hides them and loads only the ones a
prompt needs. The tool router adds a one-line hint so Claude skips tool groups that cannot help.

## How a prompt flows

1. Claude Code runs the `UserPromptSubmit` hook, `router.py prompt`.
2. The hook checks the session mode. Commands like `jev off` are handled here and never reach
   Claude.
3. Each enabled router adds its questions, and the hook sends them to Jev in one request.
4. Each router turns its answers into a sentence. The hook joins them into one line:

   ```
   [jev-router] Load skill `ponytail`: read ~/.claude/skills/ponytail/SKILL.md and follow it
   for this task. Tools not needed, skip them: web, browser, railway, figma.
   ```

5. If Jev fails, the prompt goes through untouched. Claude is pointed at a local skill index
   once per session.

Measured on this laptop: 6.7k to 7k Jev tokens and 0.55 to 0.75 s per routed prompt.

## Install

Requirements:

- Python 3.9 or newer. No packages to install.
- `TYPESAFE_API_KEY` set in the environment Claude Code starts from. On macOS, set it in your
  shell profile for the terminal and with `launchctl setenv` for the desktop app.

```sh
git clone https://github.com/0xSarnavo/jev-router ~/Development/jev.fun/jev-router
cd ~/Development/jev.fun/jev-router
python3 -m unittest discover -s tests   # optional, runs offline
python3 install.py
```

The installer:

- backs up `~/.claude/settings.json` next to itself;
- adds the `SessionStart` and `UserPromptSubmit` hooks, plus one `SessionStart` hook per
  always-on skill;
- sets each skill in `~/.claude/skills` to `user-invocable-only`, which hides it from the startup
  list but keeps its slash command working;
- records the overrides it added in `~/.cache/jev-router/installed.json`.

Start a new Claude Code session to pick up the hooks. Rerun `install.py` after changing
`always_on` or after adding skills you want hidden.

To remove everything the installer added:

```sh
python3 install.py --uninstall
```

## Control it from a session

Type these as a normal prompt.

| Prompt | Effect for this session |
| --- | --- |
| `jev smart` | Default. Route prompts, skip short or trivial ones like `ok` or `continue` |
| `jev all` | Route every prompt except slash commands |
| `jev ask` | Route only prompts that start with `jev:` |
| `jev off` | Route nothing |
| `jev skills off`, `jev tools off` | Switch one router off. `on` switches it back |
| `jev status` | Show mode, routers and skills loaded so far |

## Configure

Defaults live in `config.json`. Put your own values in `config.local.json`, which git ignores.
Top-level keys replace; router sections merge key by key:

```json
{ "default_mode": "ask", "tools": { "skip_threshold": 0.1 } }
```

| Key | Meaning |
| --- | --- |
| `model` | Jev model name, `jev-latest` by default |
| `default_mode` | Mode for new sessions |
| `timeout_s` | Jev request timeout. The hook gives up and lets the prompt through after this |
| `env_file` | A `.env` file to read `TYPESAFE_API_KEY` from if the environment lacks it |
| `smart.min_words`, `smart.skip_regex` | What smart mode treats as trivial |
| `skills`, `tools` | Router settings, described in each router's doc |

## Privacy

Routed prompt text and the project folder name go to the TypeSafe API. Use `jev ask` or `jev off`
in sessions where that is not acceptable. The local log at `~/.cache/jev-router/log.jsonl` stores
decisions, token counts, latency and a prompt hash. It never stores prompt text.

## Files

| File | Role |
| --- | --- |
| `router.py` | Hook entry point: modes, the Jev call, logging |
| `skills.py` | Skill router and skill catalog |
| `tools.py` | Tool router |
| `jev.py` | TypeSafe client, stdlib only, never logs the key |
| `install.py` | Adds and removes the hooks and skill overrides |
| `config.json` | Defaults |
