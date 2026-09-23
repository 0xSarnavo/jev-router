#!/usr/bin/env python3
"""Score Jev and Laya against hand-labelled prompts. Writes bench/results-backends.json."""
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import jev  # noqa: E402
import models  # noqa: E402
import router  # noqa: E402

TIERS = ["small", "standard", "large", "hard"]


def main():
    cfg = router.load_config()
    gates = cfg["skills"]["gated"]
    q = {"code": {"type": "noul", "instructions": gates["ponytail"]},
         "prose": {"type": "noul", "instructions": gates["no-ai-slop"]},
         "history": {"type": "noul", "instructions": gates["potpie-cli"]},
         "railway": {"type": "noul", "instructions": "Will handling the request in `prompt` need "
                     + cfg["mcp"]["describe"]["railway"] + "?"},
         "web": {"type": "noul", "instructions": "Will handling the request in `prompt` need "
                 + cfg["mcp"]["describe"]["tinyfish"] + "?"},
         **models.questions(cfg["models"], {})}
    cases = json.loads((ROOT / "bench" / "prompts.json").read_text())
    key = jev.load_key(cfg.get("env_file"))
    backends = {"jev": lambda st: jev.evaluate(key, st, q, cfg["model"], 20),
                "laya": lambda st: jev.evaluate(None, st, q, cfg["laya"]["model"], 30, cfg["laya"]["url"])}
    out = {}
    for name, call in backends.items():
        hits, lat, tier_exact, tier_near, rows = {k: 0 for k in ("code", "prose", "history", "railway", "web")}, [], 0, 0, []
        for c in cases:
            t = time.time()
            a, _ = call({"prompt": c["p"], "project": "demo-app"})
            lat.append((time.time() - t) * 1000)
            for k in hits:
                hits[k] += (a[k]["noul"] >= 0.5) == bool(c[k])
            tier, score = models.tier(cfg["models"], a)
            tier = "hard" if tier == "long" else tier
            d = abs(TIERS.index(tier) - TIERS.index(c["tier"]))
            tier_exact += d == 0
            tier_near += d <= 1
            rows.append({"p": c["p"], "tier": tier, "expected": c["tier"], "effort": score})
        n = len(cases)
        out[name] = {"n": n, "gates": {k: v / n for k, v in hits.items()},
                     "yes_no_accuracy": sum(hits.values()) / (n * len(hits)),
                     "tier_exact": tier_exact / n, "tier_within_one": tier_near / n,
                     "latency_ms_median": round(statistics.median(lat)), "rows": rows}
        print(f"{name}: yes/no {out[name]['yes_no_accuracy']:.0%}, tier exact {tier_exact}/{n}, "
              f"within one {tier_near}/{n}, median {out[name]['latency_ms_median']} ms, "
              + ", ".join(f"{k} {v:.0%}" for k, v in out[name]["gates"].items()))
    (ROOT / "bench" / "results-backends.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
