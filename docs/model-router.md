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

Code maps the answers to a tier. Jev supplies the judgment and the config owns the policy.

| Tier | Rule |
| --- | --- |
| small | effort below 1.5 and no risk |
| standard | effort 1.5 to 3 |
| large | effort 3 or more, or risk |
| long | `model:context` yes, on any tier: prefer the biggest context window in that tier or the next |

Proposed models per harness, all in `config.json`:

| Tier | Claude Code | Codex | OpenCode (free only) |
| --- | --- | --- | --- |
| small | `haiku` | `gpt-6-luna`, effort low | `opencode/mimo-v2.6-flash-free` |
| standard | `sonnet` | `gpt-6-sol`, effort medium | `opencode/big-pickle` |
| large | `opus` | `gpt-6-astra`, effort high | `opencode/nemotron-3-ultra-free` |
| long | `opus[1m]` | `gpt-6-sol`, 272k context | `opencode/muse-spark-1.3-contributor-free`, 1M context |

Codex also routes reasoning effort, which matters more there than the model. Your Codex config
runs `gpt-6-sol` at `xhigh` for every prompt, including one-line questions.

The OpenCode picks come from the catalog: every free model has tool calls and reasoning, so the
split is by speed and context size. They are a starting point to calibrate against real runs.

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

Tested on this laptop on 2026-09-23 with Claude Code 2.1.280, Codex CLI 0.155.1 and OpenCode
1.18.32.

| | Claude Code | Codex | OpenCode |
| --- | --- | --- | --- |
| Prompt hook | `UserPromptSubmit` | `UserPromptSubmit` | `chat.message` plugin hook |
| Skill and tool routers work today | Yes | Yes, unchanged | Needs a small JS plugin |
| Current model in hook input | No. Read it from the transcript, then `settings.json` | Yes, `model` field | Yes, `input.model` |
| Hook can change the model | No | No | Yes, tested |
| Hook can turn tools off | No | No | Rejected on the free tier |
| Hook can add instructions | Yes, `additionalContext` | Yes, same field | Yes, system prompt, tested |

What the tests showed:

- **Claude Code.** The prompt hook can add context, set the title or block. It has no model
  field, so ask mode blocks and auto mode hands off to a subagent. `PostModelSwitch` fires after
  `/model`, which lets the router track the current model.
- **Codex.** Its prompt hook output schema matches Claude Code's field for field. The existing
  `router.py prompt` ran as a Codex hook without changes and its line reached the model. New
  hooks need a trust entry in `~/.codex/config.toml` before they run, so the installer has to
  add one or you approve it in Codex once. No output field sets the model, so Codex gets the
  same suggest and ask modes as Claude Code. To check: whether Codex subagents accept a model
  override, which would give Codex an auto mode.
- **OpenCode.** A plugin that sets `output.message.model` in `chat.message` switched the model
  for that prompt. The run was started on `big-pickle` and the model call went to
  `mimo-v2.6-flash-free`, and the reverse worked too. Auto mode is a real per-prompt switch here,
  with no subagent. Setting `output.message.tools` to turn tools off made the free tier return
  `FreeTierError: OpenCode's free tier can only be used from within OpenCode`. So the tool router
  stays advisory there too. Adding a line to the system prompt in
  `experimental.chat.system.transform` worked, so that is where skill and tool notes go.

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

1. Model router questions and tiers in `router.py`, with suggest and ask modes for Claude Code
   and Codex. Log every rating next to the model used, so thresholds come from data.
2. Codex installer support: hooks in `~/.codex/hooks.json` plus trust entries.
3. OpenCode plugin: a thin JS file that calls `router.py` and applies the answer. Auto mode
   switches the model directly, and skill and tool notes go into the system prompt.
4. Auto mode for Claude Code through subagents, once the logs show the ratings match your own
   choices.
5. The `jev` launcher across the three CLIs.

## Open questions

- Do the proposed Codex and OpenCode tiers match how you use them?
- Should auto mode ever go below Sonnet on Claude Code, or is Haiku too weak for your work?
- Which default for new sessions: suggest, ask or auto?
- For the launcher: should Jev choose the CLI, or do you choose it and Jev only picks the model?
