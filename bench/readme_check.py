#!/usr/bin/env python3
"""Ask Jev and Laya whether README.md covers each required point. Writes bench/results-readme.json."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import jev  # noqa: E402
import router  # noqa: E402

POINTS = {
    "what": "explains in plain words what jev-router is and what problem it solves",
    "jev_or_laya": "explains what Jev and Laya are and how to choose or switch between them",
    "install": "gives the steps to install it",
    "use": "shows how to use it day to day, including the in-session commands",
    "results": "shows measured results such as token savings, accuracy or latency",
    "benchmark_backends": "compares Jev and Laya with numbers",
    "benchmark_clis": "reports results across Claude Code, Codex and OpenCode",
    "how_it_works": "explains how a prompt flows through the routers",
    "contribute": "explains how to contribute, including running the tests",
    "stack": "explains what Potpie, graphify and GSD each do in this project",
    "dogfood": "says the project uses its own router, Potpie, graphify and GSD on itself",
    "privacy": "says what data leaves the machine",
    "nontech": "has an explanation a non-technical reader can follow",
}


def main():
    cfg = router.load_config()
    readme = (ROOT / "README.md").read_text()
    q = {k: {"type": "noul", "instructions": f"Does the document in `readme` {v}?"} for k, v in POINTS.items()}
    state = {"readme": readme}
    out = {}
    runs = {"jev": lambda: jev.evaluate(jev.load_key(cfg.get("env_file")), state, q, cfg["model"], 30),
            "laya": lambda: jev.evaluate(None, state, q, cfg["laya"]["model"], 60, cfg["laya"]["url"])}
    for name, call in runs.items():
        try:
            a, meta = call()
        except jev.JevError as e:
            out[name] = {"error": str(e)}
            continue
        out[name] = {k: round(a[k]["noul"], 2) for k in POINTS}
    print(f"{'point':20} {'jev':>6} {'laya':>6}")
    for k in POINTS:
        print(f"{k:20} {out['jev'].get(k, '-'):>6} {out['laya'].get(k, '-'):>6}")
    (ROOT / "bench" / "results-readme.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
