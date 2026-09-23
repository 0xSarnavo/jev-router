# jev-router

Per-prompt routing for coding agents, powered by [Jev](https://docs.typesafe.ai), TypeSafe's
System One model. Jev returns typed answers and probabilities in well under a second, which makes
it cheap enough to run before every prompt.

There are five routers and a launcher. Each router has its own config section, can be switched
off on its own, and shares one Jev request per prompt with the others.

| Part | What it decides | Where |
| --- | --- | --- |
| [Skill router](docs/skill-router.md) | Which skill files to load for this prompt, if any | Claude Code, Codex |
| [Tool router](docs/tool-router.md) | Which built-in tool groups the prompt needs and which to skip | Claude Code, Codex |
| [MCP router](docs/mcp-router.md) | Which MCP servers the prompt needs | Hint in session, real cut at launch |
| [Model router](docs/model-router.md) | Which model and effort level should handle the prompt | Suggest, ask or auto in session |
| [Context router](docs/context-router.md) | Which earlier turns, from any CLI, the next agent should see | Claude Code, Codex, OpenCode |
| `jev` launcher | Which CLI, model, effort and MCP servers to start with | Claude Code, Codex, OpenCode |

How this fits with Potpie, graphify and GSD: [stack-plan.md](docs/stack-plan.md).

Questions go to Jev, or to Laya, an open model with the same API that runs locally. See
[Backends](docs/backends.md).

Claude Code lists every skill description at startup, and OpenCode sends every MCP tool schema on
every request. On this laptop that was about 83,000 extra tokens per OpenCode request. The routers
keep only what a prompt needs.

## How a prompt flows

1. Claude Code runs the `UserPromptSubmit` hook, `router.py prompt`.
2. The hook checks the session mode. Commands like `jev off` are handled here and never reach
   Claude.
3. Each enabled router adds its questions, and the hook sends them to Jev in one request.
4. Each router turns its answers into a sentence. The hook joins them into one line:

   ```
   [jev-router] Load skill `ponytail`: read ~/.claude/skills/ponytail/SKILL.md and follow it
   for this task. Tools not needed, skip them: web, browser. MCP servers not needed, do not
   search or call their tools: railway, tinyfish. Model: Jev rates this small (effort 0.9/4).
   Before starting, ask the user with AskUserQuestion ...
   ```

5. If Jev fails, the prompt goes through untouched. Claude is pointed at a local skill index
   once per session.

Measured on this laptop with all four routers: about 7.4k Jev tokens and 0.6 to 0.75 s per
routed prompt.

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
- adds the `SessionStart`, `UserPromptSubmit` and `Stop` hooks to Claude Code, plus one
  `SessionStart` hook per always-on skill;
- adds the same hooks to `~/.codex/hooks.json` if Codex is installed. Codex shows "Hooks need
  review" on its next start. Trust them there once;
- writes the OpenCode plugin to `~/.config/opencode/plugins/jev-router.js` if OpenCode is
  installed;
- sets each skill in `~/.claude/skills` to `user-invocable-only`, which hides it from the startup
  list but keeps its slash command working;
- records the overrides it added in `~/.cache/jev-router/installed.json`;
- links the launcher to `~/.local/bin/jev`.

Start a new Claude Code session to pick up the hooks. Rerun `install.py` after changing
`always_on` or after adding skills you want hidden.

The installer backs up each file it edits next to the original. To remove everything it added:

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
| `jev skills off`, `jev tools off`, `jev mcp off`, `jev models off` | Switch one router off. `on` switches it back |
| `jev model suggest`, `ask`, `auto`, `off` | How the model router acts. Default `ask` |
| `jev context off` | Stop handing earlier turns to this session |
| `jev backend jev`, `laya`, `auto` | Which service answers. Default `auto`: Jev, then Laya |
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
| `skills`, `tools`, `mcp`, `models` | Router settings, described in each router's doc |
| `launcher.notes` | One line per CLI that Jev reads when picking where a prompt should run |

## Privacy

Routed prompt text, the project folder name and your MCP server names go to the TypeSafe API. Use `jev ask` or `jev off`
in sessions where that is not acceptable. The local log at `~/.cache/jev-router/log.jsonl` stores
decisions, token counts, latency and a prompt hash. It never stores prompt text.

## Files

| File | Role |
| --- | --- |
| `router.py` | Hook entry point: modes, the Jev call, logging |
| `skills.py` | Skill router and skill catalog |
| `tools.py` | Tool router |
| `mcps.py` | MCP router, server discovery for each CLI, launch flags |
| `models.py` | Model router: tiers, picks, suggest, ask and auto |
| `context.py` | Context router: turn capture and handover |
| `opencode/jev-router.js` | OpenCode plugin template |
| `launch.py` | The `jev` launcher |
| `jev.py` | TypeSafe client, stdlib only, never logs the key |
| `install.py` | Adds and removes the hooks and skill overrides |
| `config.json` | Defaults |
