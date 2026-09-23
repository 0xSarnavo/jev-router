# Context router

Hands the relevant recent turns to whichever agent CLI takes the next prompt, so switching from
Claude Code to Codex or OpenCode does not mean re-explaining or pushing the whole conversation.

## Why not send everything

Each vendor caches only its own requests. The first prompt in another CLI always starts cold, so
a 100k-token Claude session pushed into Codex costs 100k uncached tokens before any work. What
the next agent needs is the intent: what was asked, what came out, what is next. The code itself
is already shared through the working tree.

## How it works

1. **Capture.** A Stop hook in each CLI appends one entry per turn to
   `~/.cache/jev-router/handoff/<repo>.jsonl`: the prompt, the final reply (first 600 chars), the
   `Handoff:` line if the reply has one, files changed per `git status`, and the transcript path.
   OpenCode captures from its plugin when a session goes idle.
2. **Ask for a handoff line.** The session-start note asks every agent to end replies that change
   work with `Handoff: <what is being done> | next: <next step>`, under 25 words. With the
   always-on i-have-adhd skill these come out as the next action first.
3. **Select, do not summarise.** On a prompt in a different session, up to the last 12 entries
   from other sessions in the same repo, from the last 48 hours, each get one yes/no question:
   does this prompt continue, depend on or refer to that turn? Jev picks. Nothing is rewritten, so
   what arrives is the exact text the earlier agent wrote.
4. **Inject within a budget.** Picked entries go in newest first, up to 1,800 characters, with
   the earlier transcript path for anything more. Each entry is handed over once per session.
5. **Point at project memory.** The first handover in a session also lists what exists in the
   repo: GSD state at `.planning/STATE.md`, the graphify graph at `.planning/graphs/`, and Potpie.
   They are pointers, read only if needed.

Tested on this repo on 2026-09-23. An OpenCode turn on the free Muse Spark model explained
`ask()` in `jev.py`. A Codex prompt in the same repo was told to answer from the handover only,
without reading files, and did:

```
ask() sends questions to the Jev System One API ... in `auto` mode, it falls back to Laya for
compatible questions and returns answers with backend metadata.
```

Jev offered 3 earlier turns and picked 2.

## Config

```json
"context": {
  "enabled": true,
  "threshold": 0.6,
  "max_age_h": 48,
  "scan": 12,
  "keep": 200,
  "budget_chars": 1800,
  "reply_chars": 600
}
```

| Key | Meaning |
| --- | --- |
| `threshold` | Minimum yes probability for a turn to be handed over |
| `max_age_h` | Ignore turns older than this |
| `scan` | How many recent entries to consider per prompt, one Jev question each |
| `keep` | Entries kept per repo |
| `budget_chars` | Most handover text injected per prompt |

`jev context off` switches it off for a session. The handoff log stays on this machine.
