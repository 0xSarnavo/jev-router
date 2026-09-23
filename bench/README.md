# Benchmarks

Scripts that produce the numbers in the main README. Each writes a `results-*.json` next to it.
Jev needs `TYPESAFE_API_KEY`. Laya needs a local server, see [../docs/backends.md](../docs/backends.md).

| Script | Measures | Cost | Time |
| --- | --- | --- | --- |
| `backends.py` | Jev and Laya against 20 hand-labelled prompts in `prompts.json` | About 150k Jev tokens | About 1 min |
| `handover.py` | A fact passed between every pair of Claude Code, Codex and OpenCode | Six Haiku, six GPT-6 Luna and six free OpenCode runs | About 3 min |
| `readme_check.py` | Whether README.md covers each point it is meant to | One Jev and one Laya request | Seconds |

Run from the repo root, for example `python3 bench/backends.py`.

## README coverage, latest run

Probability of yes for "does the README ...", 2026-09-23:

| Point | Jev | Laya |
| --- | --- | --- |
| explains in plain words what jev-router is and what problem it solves | 0.98 | 0.69 |
| explains what Jev and Laya are and how to choose or switch between them | 0.98 | 0.44 |
| gives the steps to install it | 0.99 | 0.84 |
| shows how to use it day to day, including the in-session commands | 0.97 | 0.67 |
| shows measured results such as token savings, accuracy or latency | 0.99 | 0.79 |
| compares Jev and Laya with numbers | 0.99 | 0.22 |
| reports results across Claude Code, Codex and OpenCode | 0.98 | 0.80 |
| explains how a prompt flows through the routers | 0.98 | 0.95 |
| explains how to contribute, including running the tests | 0.99 | 0.77 |
| explains what Potpie, graphify and GSD each do in this project | 0.97 | 0.25 |
| says the project uses its own router, Potpie, graphify and GSD on itself | 0.98 | 0.86 |
| says what data leaves the machine | 0.97 | 0.64 |
| has an explanation a non-technical reader can follow | 0.94 | 0.59 |
| walks a new user through setup step by step, including prerequisites and how to check it works | 0.98 | 0.66 |
| says what to do after adding a new skill, MCP server, model or agent CLI | 0.97 | 0.89 |

Jev rates every point as covered. Laya's low scores come mostly from its input window: the
English checkpoint reads about 320 tokens of state per question, and the README is about 2,000
words. Given only the relevant section, Laya's score rose from 0.44 to 0.69 on the Jev-or-Laya
point, 0.22 to 0.41 on the backend benchmark, and 0.25 to 0.69 on the stack. For long documents,
send Laya one section per question.

## Notes

`handover.py` sets `PWD` for each child process. OpenCode resolves its project from `$PWD`,
which Python's `subprocess` does not update when it changes directory, so without it OpenCode
files every turn under the directory the script was started from.
