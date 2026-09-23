# Coding across agents: the stack and how it fits

This is the reference for how jev-router, Potpie, graphify and GSD work together when Claude
Code, Codex and OpenCode share one repo. Part of it is built. The rest is the plan, in order.

Tried on this repo on 2026-09-23. Numbers below come from that run.

## One job each

| Tool | Answers | Lives in | Read by any CLI? | Cost to use |
| --- | --- | --- | --- | --- |
| jev-router | Which skills, tools, MCP servers, model and earlier turns this prompt needs | Hooks, `~/.cache/jev-router/` | Yes, hooks in all three | About 7.5k Jev tokens and 0.6 s per prompt, none in the agent's context beyond one note |
| Potpie | Why things are the way they are: decisions, features, past bugs | Local daemon, `~/.potpie/` | Yes, it is a CLI | One `search-entities` call returns 300 to 900 tokens, 2 to 3 s |
| graphify | What calls what, where a symbol is used, what a change touches | `.planning/graphs/graph.json` in the repo | Yes, it is a CLI | `graphify explain <symbol>` returns about 800 characters in 0.15 s. Rebuild takes 2.5 s, no API cost |
| GSD | What we are doing and where we stopped: phases, plans, state, handoffs | `.planning/*.md` and `.json` in the repo | Yes, plain files. The skills are on Claude Code and OpenCode, not Codex | Reading `STATE.md` or `.continue-here.md` is a few hundred tokens |
| Code and git | What the code is now | The working tree | Yes | Free to the next agent, it reads files |

They overlap less than they look. Potpie holds reasons, graphify holds structure, GSD holds the
plan and progress, and the handover holds the last few turns of intent. None of them should be
loaded whole into an agent's context.

## Rules against bloat

1. **Pointers, not content.** A note names a file or a command. The agent runs it when it needs
   the answer. This is how the skill router already works.
2. **One small answer, inline, only when a gate fires.** If Jev is confident a prompt needs a
   specific fact, one capped query result can go in the note. Never more than one per source.
3. **Never the whole graph or whole memory.** `gsd-tools.cjs graphify query` dumped 149 KB, about
   37k tokens, for one query. Use `graphify explain` or `graphify path`.
4. **Write-back is opt-in.** Recording decisions into Potpie needs a proposal step, so agents
   do it when asked or through a skill, not from a hook on every turn.
5. **Slow checks stay out of the prompt hook.** `potpie pot linked` takes about 2 s, so the router
   reads `~/.potpie/pots.json` directly instead.

## Built

- **Handover between CLIs.** Stop hooks in Claude Code and Codex, and the OpenCode plugin,
  record each turn. On the next prompt in another session, Jev picks the relevant turns. See
  [context-router.md](context-router.md). Tested OpenCode to Codex on this repo.
- **Project memory pointers.** The first handover in a session lists what exists for this repo:
  the GSD handoff file if there is one, the graphify command with the graph path, and the Potpie
  pot with the search command. On this repo:

  ```
  Code graph: `graphify explain <symbol> --graph .planning/graphs/graph.json` for callers and
  callees. Never dump the whole graph; Potpie pot `jev-router`:
  `potpie --json graph search-entities "<question>" --limit 3` for past decisions.
  ```

- **Potpie is routed like a skill.** The `potpie-cli` gate fires only when the prompt needs
  recorded history, not for ordinary coding.

## Planned, in order

1. **graphify gate.** A yes/no question: does the prompt ask what uses, calls or would be broken
   by a named symbol? If yes, the hook runs `graphify explain` for symbols it finds in the prompt
   and puts the result in the note, capped at 1,000 characters. Cheap, since the call is 0.15 s
   and local.
2. **Keep the graph fresh.** In the Stop hook, when `git status` shows changed code files and a
   graph exists, run `graphify update .` in the background. 2.5 s, no API cost.
3. **Potpie answer inline.** When the potpie gate fires above 0.8, run one `search-entities`
   with the prompt, limit 2, and add the top results to the note. Recall ranking was weak in the
   trial, so check the log for a week before trusting it.
4. **GSD resume.** When `.planning/.continue-here.md` or `HANDOFF.json` exists and the prompt is
   about continuing work, point at it and let the skill router pick `gsd-resume-work`.
5. **Codex gets GSD.** GSD is on Claude Code (1.42.3) and OpenCode (1.20.4, older) but not Codex.
   Its files still work there through the handover pointers. Installing it for Codex, and
   updating OpenCode's copy, would let Codex run the resume flow itself.
6. **Decision capture, opt-in.** A `jev remember` prompt command that asks the current agent to
   propose the session's decisions to Potpie through the potpie skills.

## Which tool for which question

Written for agents and for Jev's gate questions:

| The prompt asks | Use |
| --- | --- |
| Why did we choose X, when did Y change, did we try Z before | Potpie search |
| What calls X, what breaks if I change X, where is X used | graphify explain or path |
| Where did we stop, what is next in this phase | GSD handoff or state file |
| What did the other agent just do | The jev-router handover note |
| What does this code do now | Read the file |

## Not planned

- **A shared cache across vendors.** It does not exist. Each switch starts cold, which is why
  the handover stays small.
- **Another memory store.** Potpie, GSD files and the handover log cover reasons, plans and
  recent intent. A fourth would add context without a new kind of answer.
