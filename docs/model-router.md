# Model router (plan)

Status: planned, not built. The skill and tool routers are done. This is the design for the
third router, open for review.

## Goal

Before the main model spends tokens, Jev rates the prompt and names the cheapest model that can
do it well. A one-line question should not run on Opus. A cross-file refactor should not run on
Haiku. The same rating should work across Claude Code, Codex and OpenCode, and pick between them.

## What Jev is asked

The model router adds a few questions to the request the other routers already send, so it
costs about 300 extra Jev tokens and no extra latency.

| Id | Type | Question |
| --- | --- | --- |
| `model:effort` | Score, 5 levels | How much reasoning the task needs: lookup or one-liner, small single-file change, normal feature or bug, multi-file design or tricky debugging, open-ended architecture or research |
| `model:context` | Noul | Does the task need a lot of the repo or conversation in view at once? |
| `model:risk` | Noul | Would a wrong answer be costly: data loss, security, production, money? |

Code maps the answers to a tier. Jev supplies the judgment and the config owns the policy:

| Tier | Rule | Claude Code | Codex | OpenCode |
| --- | --- | --- | --- | --- |
| small | effort below 1.5, no risk | `haiku` | a mini model | a free or flash model |
| standard | effort 1.5 to 3 | `sonnet` | default model | chosen default |
| large | effort 3 or more, or risk | `opus` | top model, high effort | chosen top model |

All model names go in `config.json`, per harness, so nothing is hard-coded.

## Behaviour: suggest, ask, auto

Set per session like the other routers: `jev model suggest|ask|auto|off`.

- **suggest.** Adds a line such as "Jev rates this small. Sonnet would do." Claude shows it at
  the top of its answer. You switch with `/model` if you want to. Costs nothing, saves nothing
  on the current prompt.
- **ask.** When the tier is below the current model, the hook blocks the prompt before Claude
  sees it and shows: "Small task. Run /model sonnet, then press up and enter to resend. Resend
  now to keep Opus." A resend of the same prompt within two minutes passes straight through.
  No Opus tokens are spent on the blocked attempt.
- **auto.** The hook tells Claude to hand the task to a subagent on the routed model through the
  Agent tool, then pass the result back. The main model spends a few hundred tokens on the
  hand-off and the subagent does the work. Only for small and standard tiers, and only when the
  task does not depend on earlier conversation.

Upgrades work the same way in reverse. On Sonnet, a large-tier prompt gets "This looks hard.
Opus may do better." It is never automatic, because upgrades cost more.

## What each harness allows

Checked on this laptop against Claude Code 2.1.280, Codex CLI 0.155.1 and OpenCode 1.18.32.

- **Claude Code.** A `UserPromptSubmit` hook can add context, set the session title or block the
  prompt. It cannot change the model. That is why ask blocks and auto delegates. A
  `PreModelSwitch` hook can allow or deny a switch and `PostModelSwitch` can add context after
  one, which the router can use to note the new model in the session state. To verify: whether
  the hook input carries the current model, or whether the router has to track it from
  `/model` commands and the settings file.
- **Codex.** Has `session_start`, `user_prompt_submit`, `pre_tool_use` and `subagent_start`
  hooks in `~/.codex/hooks.json`. The skill and tool routers should port with a small output
  adapter. To verify: the output schema, and whether any hook can pick the model.
- **OpenCode.** Has a JavaScript plugin system in `~/.config/opencode/plugins`. To verify:
  whether a plugin hook can set the model for one message. If it can, auto mode becomes a real
  per-prompt switch there, with no subagent needed.

## Switching between CLIs

None of the three can hand a live session to another. Switching harness means starting a new
session, so it belongs in a launcher, not a hook:

```sh
jev "rename the prop across the app"         # Jev picks harness and model, then runs it
jev --ask "add rate limiting to the api"     # shows the pick and waits for enter
jev --use codex "..."                        # fixed harness, Jev still picks the model
```

The launcher asks Jev the same effort questions plus one choice over the enabled harnesses,
using a short strengths note for each from config. Then it runs `claude --model <m> "<prompt>"`,
`codex -m <m> "<prompt>"` or `opencode run -m <provider/model> "<prompt>"`.

## Build order

1. Claude Code model router with suggest and ask. Log every rating next to the model actually
   used, so thresholds come from data.
2. Auto mode through subagents, after the logs show the ratings match your own choices.
3. The `jev` launcher across the three CLIs.
4. Codex adapter for all three routers.
5. OpenCode plugin, once the per-message model question is answered.

## Open questions

- Which models count as small, standard and large for you on Codex and OpenCode?
- Should auto mode ever go below Sonnet on Claude Code, or is Haiku too weak for your work?
- Which default for new sessions: suggest, ask or auto?
- For the launcher: should Jev choose the CLI, or do you choose it and Jev only picks the model?
