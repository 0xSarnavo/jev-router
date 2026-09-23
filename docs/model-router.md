# Model router

Rates how much model a prompt needs, then suggests, asks about or applies the cheapest model and
effort level that should do it well.

## What it asks Jev

Three questions, sent in the same request as the other routers:

| Id | Type | Question |
| --- | --- | --- |
| `model:effort` | Score, 0 to 4 | Lookup or one-liner, small single-file change, normal feature or fix, multi-file design or tricky debugging, open-ended architecture or long task |
| `model:risk` | Noul | Would a wrong result be costly: data loss, security, production, payments, migrations? |
| `model:context` | Noul | Does the prompt need a very large amount of code, logs or documents in view at once? |

Code turns the answers into a tier:

| Tier | Rule |
| --- | --- |
| small | effort below 1.5 |
| standard | effort 1.5 to 2.5 |
| large | effort 2.5 to 3.5, or any tier with risk at 0.6 or more |
| hard | effort 3.5 or more |
| long | context at 0.6 or more, on any tier above small |

Ratings from live runs:

| Prompt | Effort | Tier |
| --- | --- | --- |
| what does the useEffect cleanup function do | 0.04 | small |
| rename the Button prop variant to tone in the header component | 1.31 | small |
| add a pricing page with three plans and a monthly yearly toggle | 2.08 | standard |
| our checkout sometimes double charges customers, find out why and fix it | 2.97 | large |
| deploy the website to railway and check the logs for errors | 3.04 | large |
| redesign the whole auth architecture to support SSO and multi-tenant orgs | 4.0 | long |

## Models per tier

| Tier | Claude Code | Codex | OpenCode (free) |
| --- | --- | --- | --- |
| small | haiku, low | gpt-6-luna, low | muse-spark-1.3 |
| standard | sonnet, medium | gpt-6-sol, medium | muse-spark-1.3 |
| large | opus, medium | gpt-6-sol, max | muse-spark-1.3 |
| hard | opus, xhigh | gpt-6-astra, high | muse-spark-1.3 |
| long | opus[1m], medium | gpt-6-sol, medium | muse-spark-1.3 (1M context) |

Why these, from launch coverage in the week of 2026-09-22. Numbers come from the linked write-ups,
not from runs here:

- **Opus 5.5 leads hard agentic coding.** On Terminal-Bench 4.0 it scores 52.5% at medium and
  59.6% at xhigh. GPT-6 Sol scores 43.9% at max and 30.3% at xhigh. GPT-6 Astra ties Opus 5.5 at
  59.6% and costs $10/$50 per million tokens against $4/$20.
- **Sol is Sonnet-priced.** Both cost $2/$10. Sol is cheaper than Opus for any target score
  below about 44 on the Intelligence Index, so it is the Codex standard tier.
- **Luna is the cheapest option by far,** at $0.10/$0.50 against Haiku 4.5 at $1/$5. The
  launcher sends small tasks to Codex for that reason.
- **More effort is not always better.** Opus 5.5 at medium beat its own max on FrontierCode.
  On Terminal-Bench, xhigh is the peak and max adds nothing, so the hard tier stops at xhigh.
  Codex `ultra` runs max over about four parallel subagents and only helps when the work splits
  cleanly, so no tier uses it.
- **Astra leads math, science and computer use** in OpenAI's own figures. That is written into
  the launcher's note for Codex.
- **Long context:** Sol charges double input above 272k tokens. Opus 5.5 has no surcharge.

Sources: codingfleet.com/blog/claude-opus-5-5-vs-gpt-6-sol,
kingy.ai/blog/claude-opus-5-5-vs-gpt-6-astra-vs-gpt-5-6-sol,
agiflow.io/blog/codex-model-thinking-effort-guide, venturebeat.com coverage of the Opus 5.5
launch. Sonnet 5 and Haiku 4.5 benchmark numbers were not verified.

## In a session: suggest, ask, auto

Set with `jev model suggest|ask|auto|off`. The default is `ask`.

Claude Code and Codex hooks cannot change the model. So the router only acts when the tier's
model ranks above or below the current one:

| Mode | Claude Code | Codex |
| --- | --- | --- |
| suggest | Claude names the recommended model in one line | Same |
| ask | Claude asks with a picker first: the recommendation, or keep the current model. Picking the cheaper one runs the task in a Sonnet or Haiku subagent | The prompt is blocked with "Run /model and pick gpt-6-luna at low effort, then resend." Resending the same prompt keeps the current model |
| auto | Claude hands small and standard tasks to a subagent on the cheaper model | Falls back to suggest |

Ask mode asks once per tier per session, then falls back to a one-line suggestion. Upgrades are
never automatic. On Haiku, a hard prompt only gets "opus at xhigh effort may do better".

Claude Code does not pass the current model to hooks, so the router reads it from the session
transcript and falls back to `model` in `~/.claude/settings.json`. Codex passes it directly.

## At launch: `jev`

```sh
jev "add a pricing page"          # Jev rates it, you pick from a numbered list, the CLI starts
jev --use codex "..."             # fixed CLI, Jev picks model, effort and MCP servers
jev --yes "..."                   # take the recommendation
jev --dry "..."                   # print the command only
```

Example:

```
Jev: large task, effort 2.97/4 (642 ms).
  1. claude: opus at medium effort (recommended). MCP: railway, tinyfish, drops logos-copilot, figma
  2. codex: gpt-6-sol at max effort. MCP: railway, node_repl
  3. opencode: opencode/muse-spark-1.3-contributor-free. MCP: railway, tinyfish, drops figma, higgsfield
Pick 1-3 [1], or q to quit:
```

Jev picks the first CLI from the notes in `launcher.notes`, weighing quality first and cost
second. The others follow with the same tier. The command it runs:

| CLI | Command |
| --- | --- |
| Claude Code | `claude --model <m> --effort <e> [mcp flags] "<prompt>"` |
| Codex | `codex -m <m> -c model_reasoning_effort="<e>" [mcp flags] "<prompt>"` |
| OpenCode | `opencode -m <m> --prompt "<prompt>"` |

## What each CLI allows

Tested on 2026-09-23 with Claude Code 2.1.280, Codex CLI 0.155.1 and OpenCode 1.18.32.

| | Claude Code | Codex | OpenCode |
| --- | --- | --- | --- |
| Current model in hook input | No, read from transcript | Yes | Yes |
| Hook can change the model | No | No | Yes, from a plugin |
| Hook can turn tools off | No | No | Rejected on the free tier |
| Hook can add instructions | Yes | Yes | Yes, system prompt |

The routers run in Codex unchanged, because its prompt hook output matches Claude Code's. New
Codex hooks need a trust entry before they run. OpenCode needs a small plugin, not built yet: it
would call `router.py`, set the model on the message and add notes to the system prompt.

## Next

- OpenCode plugin with real per-prompt model switching.
- Codex installer support, including hook trust.
- Laya (huggingface.co/convaiinnovations/laya) as a local fallback when Jev is down. It serves the
  same `/v1/systemone` API, but degrades past about 20 choice options, so it could answer the
  model, tool and MCP questions but not the skill pick.

## Config

```json
"models": {
  "enabled": true,
  "mode": "ask",
  "risk_threshold": 0.6,
  "context_threshold": 0.6,
  "tiers": { "claude": { "small": ["haiku", "low"] } },
  "rank": { "claude": ["haiku", "sonnet", "opus", "fable"], "codex": ["luna", "sol", "astra"] },
  "claude_subagent": { "small": "haiku", "standard": "sonnet" }
}
```

`rank` orders model families from cheapest to strongest, matched as substrings of the model id.
`claude_subagent` sets which tiers may be handed to a subagent in ask and auto mode. Remove
`small` to never go below Sonnet.
