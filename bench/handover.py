#!/usr/bin/env python3
"""Hand a fact from one agent CLI to another through jev-router, for every pair.

Each pair runs in a fresh git repo so only that pair's turn can be handed over.
Uses cheap models: Claude haiku, Codex gpt-6-luna at low effort, OpenCode's free Muse Spark.
Writes bench/results-handover.json.
"""
import itertools
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUN = {
    "claude": lambda p: ["claude", "-p", "--model", "haiku", p],
    "codex": lambda p: ["codex", "exec", "-m", "gpt-6-luna", "-c", 'model_reasoning_effort="low"',
                        "--dangerously-bypass-hook-trust", "-s", "read-only", "--skip-git-repo-check", p],
    "opencode": lambda p: ["opencode", "run", "-m", "opencode/muse-spark-1.3-contributor-free", p],
}
WORDS = ["AMBERFOX", "BLUEHERON", "COPPERELK", "DUSKOWL", "EMBERLYNX", "FROSTWREN"]


def run(cli, prompt, cwd):
    t = time.time()
    # OpenCode resolves its project from $PWD, which subprocess does not update.
    r = subprocess.run(RUN[cli](prompt), cwd=cwd, env={**os.environ, "PWD": cwd},
                       stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=300)
    return r.stdout + r.stderr, round(time.time() - t, 1)


def main():
    results = []
    for (a, b), word in zip(itertools.permutations(RUN, 2), WORDS):
        repo = tempfile.mkdtemp(prefix=f"jr-{a}-{b}-")
        subprocess.run(["git", "init", "-q"], cwd=repo)
        Path(repo, "notes.md").write_text("# release\n")
        _, t1 = run(a, f"We are preparing the next release. Its codename is {word}. Do not edit any "
                       "files. Reply in one short sentence, then a Handoff line with the codename.", repo)
        out, t2 = run(b, "Continue the release work the previous agent started. What codename did it "
                         "record? Do not read or search any files. Answer from context only.", repo)
        ok = word in out
        results.append({"from": a, "to": b, "passed": ok, "first_s": t1, "second_s": t2})
        print(f"{a:8} -> {b:8} {'PASS' if ok else 'FAIL'}  ({t1}s, {t2}s)", flush=True)
    (ROOT / "bench" / "results-handover.json").write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
