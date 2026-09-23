#!/usr/bin/env python3
"""Generate a public test set whose labels come from the spec each prompt was written to.

Uses `claude -p --model haiku` with hooks disabled. Writes bench/public-eval.json. The prompts
are synthetic, so the set can be published and anyone can score a model on it.
"""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = {"code": 0, "prose": 0, "history": 0, "railway": 0, "web": 0, "github": 0, "browser": 0}
SPECS = [
    ("a small code change to one file: rename, typo, tweak a value, fix one obvious bug", {"code": 1}, "small"),
    ("a normal feature or bug fix touching a few files in a web app", {"code": 1}, "standard"),
    ("a risky code change: payments, auth, production database migrations, data deletion", {"code": 1}, "large"),
    ("an open-ended architecture redesign or long multi-step engineering project", {"code": 1}, "hard"),
    ("a question asking to explain existing code or a concept, with no change requested", {}, "small"),
    ("a request to write or edit prose people will read: a post, email, release notes, docs page, landing copy", {"prose": 1}, "small"),
    ("a question about why or when something in the project was decided, changed or broken in the past", {"history": 1}, "small"),
    ("a request to deploy, inspect logs, or change settings of a service hosted on Railway", {"railway": 1}, "standard"),
    ("a request to search the web or read live web pages for current information", {"web": 1}, "small"),
    ("a request involving GitHub pull requests, issues, CI checks or releases via the gh CLI", {"github": 1}, "small"),
    ("a request to drive a real browser: click through a site, fill a form, take screenshots", {"browser": 1}, "standard"),
    ("a short conversational reply with no task, like thanks, ok, or looks good", {}, "small"),
]


def generate(spec, n=12):
    prompt = (f"Write {n} different, realistic prompts a developer might type to an AI coding agent. "
              f"Each must be {spec}. Vary length, tone, tech stack and wording; some terse, some detailed, "
              "some with typos. Output only a JSON array of strings, nothing else.")
    out = subprocess.run(["claude", "-p", "--model", "haiku", "--settings", '{"disableAllHooks": true}', prompt],
                         capture_output=True, text=True, timeout=300, stdin=subprocess.DEVNULL).stdout
    start, end = out.find("["), out.rfind("]")
    return json.loads(out[start:end + 1])


def main():
    rows = []
    for spec, labels, tier in SPECS:
        for p in generate(spec):
            rows.append({"p": p, **BASE, **labels, "tier": tier, "spec": spec})
        print(f"{len(rows)} prompts", flush=True)
    (ROOT / "bench" / "public-eval.json").write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
