#!/usr/bin/env python3
"""Score a backend on bench/public-eval.json, the synthetic set anyone can check.

Labels come from the spec each prompt was written to, not from any model.

  python3 bench/public_eval.py jev
  python3 bench/public_eval.py laya [url]      default http://127.0.0.1:8321/v1/systemone
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import jev  # noqa: E402
import mcps  # noqa: E402
import models  # noqa: E402
import router  # noqa: E402
import skills  # noqa: E402
import tools  # noqa: E402

LABELS = {"code": "gate:ponytail", "prose": "gate:no-ai-slop", "history": "gate:potpie-cli",
          "railway": "mcp:railway", "web": "tool:web", "github": "tool:github", "browser": "tool:browser"}
TIERS = ["small", "standard", "large", "hard"]


def question_set(cfg):
    """The router's questions, minus the skill pick, which has too many options for Laya."""
    ctx = {"state_dir": router.STATE_DIR, "mcp_names": list(mcps.servers("claude", None))}
    q = {}
    for mod, c in ((skills, cfg["skills"]), (tools, cfg["tools"]), (mcps, cfg["mcp"]), (models, cfg["models"])):
        q.update(mod.questions(c, ctx))
    return {k: v for k, v in q.items() if jev.laya_fits(v, cfg["laya"]["max_options"])}


def main():
    backend = sys.argv[1] if len(sys.argv) > 1 else "jev"
    cfg = router.load_config()
    q = {k: v for k, v in question_set(cfg).items() if k in LABELS.values() or k == "model:effort"}
    rows = json.loads((ROOT / "bench" / "public-eval.json").read_text())
    if backend == "jev":
        key = jev.load_key(cfg.get("env_file"))
        call = lambda st: jev.evaluate(key, st, q, cfg["model"], 30)
    else:
        url = sys.argv[2] if len(sys.argv) > 2 else cfg["laya"]["url"]
        call = lambda st: jev.evaluate(None, st, q, cfg["laya"]["model"], 60, url)
    said = {k: [] for k in LABELS}
    tier_exact = tier_near = 0
    t0 = time.time()
    for r in rows:
        a, _ = call({"prompt": r["p"], "project": "demo-app"})
        for k, qid in LABELS.items():
            said[k].append(a[qid]["noul"] >= 0.5)
        s = a["model:effort"]["score"]
        d = abs(sum(s >= c for c in (1.5, 2.5, 3.5)) - TIERS.index(r["tier"]))
        tier_exact += d == 0
        tier_near += d <= 1
    out = {"backend": backend, "n": len(rows), "labels": {}}
    for k in LABELS:
        truth = [bool(r[k]) for r in rows]
        pos = [s for s, t in zip(said[k], truth) if t]
        neg = [not s for s, t in zip(said[k], truth) if not t]
        out["labels"][k] = {"accuracy": round(sum(s == t for s, t in zip(said[k], truth)) / len(rows), 3),
                            "recall_yes": round(sum(pos) / len(pos), 3) if pos else None,
                            "balanced": round((sum(pos) / len(pos) + sum(neg) / len(neg)) / 2, 3)}
    out["balanced_mean"] = round(sum(v["balanced"] for v in out["labels"].values()) / len(LABELS), 3)
    out["tier_exact"] = round(tier_exact / len(rows), 3)
    out["tier_within_one"] = round(tier_near / len(rows), 3)
    out["seconds"] = round(time.time() - t0)
    print(json.dumps(out, indent=1))
    res = ROOT / "bench" / "results-public.json"
    allr = json.loads(res.read_text()) if res.exists() else {}
    allr[backend if backend == "jev" else sys.argv[3] if len(sys.argv) > 3 else backend] = out
    res.write_text(json.dumps(allr, indent=1))


if __name__ == "__main__":
    main()
