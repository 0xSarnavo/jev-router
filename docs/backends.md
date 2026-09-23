# Backends: Jev and Laya

Every router question goes to one of two services with the same API, `POST /v1/systemone`.

| Backend | What it is | Where it runs |
| --- | --- | --- |
| Jev | TypeSafe's hosted System One model | api.typesafe.ai, needs `TYPESAFE_API_KEY` |
| Laya | Open-weight model with the same API, huggingface.co/convaiinnovations/laya | Your machine, no key |

`backend` in the config, or `jev backend jev|laya|auto` in a session:

- `jev`: Jev only. If it fails, the prompt goes through without routing.
- `laya`: Laya only.
- `auto`: Jev first, Laya if Jev fails. The default.

Laya degrades past about 20 choice options, so questions with more options are never sent to it.
That drops the skill pick, which has one option per skill. The skill gates, tool, MCP, model and
context questions all fit. When Laya answers, the model router only suggests and never asks or
switches, because its effort ratings were not reliable enough to act on.

## Measured on this laptop

Same 14 questions, 7 prompts, 2026-09-23, Laya 0.3.7 English checkpoint on CPU:

| | Jev | Laya |
| --- | --- | --- |
| Average latency | 605 ms | 1,511 ms |
| Yes/no agreement with Jev | | 79 of 91, 87% |

Where Laya was wrong in ways that matter:

- It rated "our checkout sometimes double charges customers" at 0.18 for risk. Jev said 0.93.
- It said the web search prompt did not need TinyFish (0.40 against 0.82).
- Its effort scores stayed between 1.4 and 2.3 for everything, from a one-line question to a
  multi-step deploy. Jev ranged from 0.04 to 3.06.

So Laya is a working offline fallback, not a replacement. It also loads with an uncalibrated
temperature warning, which its README says to fix by re-fitting on your own labels.

## Does Laya need training for this work?

For yes/no questions, stock Laya is usable as a fallback: 89% against Jev's 99% on the labelled set.
For the model tier it is not. Its effort scores stayed between 1.22 and 3.03 across 20 prompts,
where Jev ranged from 0.01 to 4.0, and moving the tier cutoffs does not fix that: the best
cutoffs fitted to those 20 prompts reached 13 of 20 exact, against 11 with the defaults and 18 for
Jev. That is why the model router only suggests when Laya answered.

## Alternative: laya-coding-router

[laya-coding-router](https://github.com/0xSarnavo/laya-coding-router) is Laya fine-tuned for these
exact questions. It serves the same `/v1/systemone` API, so it drops in wherever stock Laya does:
start its server, keep `laya.url` pointing at it, and choose `jev backend laya` or `auto`. It is
still training. Its repo has the current results and a public test set.

## Running Laya

```sh
python3 -m venv ~/.cache/jev-router/laya-venv
~/.cache/jev-router/laya-venv/bin/pip install "laya[serve]==0.3.7"
LAYA_HOST=127.0.0.1 LAYA_PORT=8321 LAYA_MODELS=english \
  ~/.cache/jev-router/laya-venv/bin/laya-serve
```

Set `LAYA_HOST=127.0.0.1`. The default is `0.0.0.0`, which serves the model to your whole
network. The first start downloads about 800 MB. `laya.url` in the config points at
`http://127.0.0.1:8321/v1/systemone`.
