# Skill router

Loads skills when a prompt needs them instead of listing every skill at session start.

## What it does

At install, every skill in `~/.claude/skills` is set to `user-invocable-only`. Claude no longer
sees their descriptions at startup, and you can still run any of them as a slash command.

On each routed prompt the skill router asks Jev two kinds of question:

- **Gates.** One yes/no question per gated skill. A gate fires when its probability reaches
  `gate_threshold`. Gates suit skills that depend on the kind of work, not on the topic:

  | Skill | Fires when |
  | --- | --- |
  | `ponytail` | The prompt asks to write, change, fix, refactor or design code |
  | `no-ai-slop` | The prompt asks for prose people will read: posts, emails, docs, copy |
  | `potpie-cli` | The answer depends on recorded project history, not the current code |

- **Pick.** One choice over every other skill plus `none`. The top option loads when its
  probability reaches `pick_threshold`.

Each skill loads once per session. Later prompts that match it get "Already active" instead of a
second copy. The list resets on session start, `/clear` and after compaction.

Always-on skills skip routing. Their full text is injected at session start, one hook per skill,
because Claude Code cut off a 13 KB hook output while 7 KB outputs arrived whole.

## Config

```json
"skills": {
  "enabled": true,
  "always_on": ["i-have-adhd", "caveman"],
  "gated": { "ponytail": "Does `prompt` ask the coding assistant to write, change ..." },
  "never_route": [],
  "gate_threshold": 0.6,
  "pick_threshold": 0.45
}
```

| Key | Meaning |
| --- | --- |
| `always_on` | Skills injected in full at every session start |
| `gated` | Skill name to yes/no question. Refer to the prompt as `` `prompt` `` |
| `never_route` | Skills Jev should never pick |
| `gate_threshold` | Minimum yes probability for a gate |
| `pick_threshold` | Minimum probability for the picked skill |

## Tuning

Write a gate question about the kind of work, and say what counts as no. The first potpie
question, "would answering depend on past decisions", fired at 0.8 on a navbar bug fix.
Rewording it to ask whether the answer must come from recorded history rather than current code
dropped that to 0.03 and kept 0.97 on "why did we remove the design system folder".

`~/.cache/jev-router/log.jsonl` records the picked skill and its probability for every prompt.
Use it to set thresholds from real prompts instead of guesses.

The skill catalog is rebuilt when a `SKILL.md` is added, removed or edited. The markdown copy at
`~/.cache/jev-router/catalog.md` is the fallback when Jev is unreachable.
