import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["JEV_ROUTER_STATE"] = tempfile.mkdtemp()

import catalog  # noqa: E402
import jev  # noqa: E402
import router  # noqa: E402


def noul(p):
    return {"type": "noul", "noul": p}


def fake_answers(cfg, skill="none", p=0.9, gates=None, tools=None):
    a = {"skill": {"type": "choice", "choice": skill, "probabilities": {skill: p}, "confidence": p}}
    for g in cfg["gated_skills"]:
        a[f"gate:{g}"] = noul((gates or {}).get(g, 0.05))
    for t in cfg["tool_groups"]:
        a[f"tool:{t}"] = noul((tools or {}).get(t, 0.05))
    return a


class Base(unittest.TestCase):
    def setUp(self):
        self.skills = tempfile.mkdtemp()
        for name in ("ponytail", "caveman", "use-railway", "no-ai-slop", "potpie-cli", "i-have-adhd"):
            d = Path(self.skills, name)
            d.mkdir()
            (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: >\n  Does {name} things. More.\n---\n\nBody of {name}.\n")
        router.STATE_DIR = Path(tempfile.mkdtemp())
        self.patch = mock.patch.object(catalog, "SKILLS_DIR", Path(self.skills))
        self.patch.start()
        self.load = mock.patch.object(catalog, "load", lambda out: catalog.build(out, Path(self.skills)))
        self.load.start()
        self.cfg = router.load_config()

    def tearDown(self):
        self.patch.stop()
        self.load.stop()

    def run_hook(self, fn, data):
        buf = io.StringIO()
        with redirect_stdout(buf):
            fn(data, self.cfg)
        out = buf.getvalue().strip()
        return json.loads(out) if out else None


class TestCatalog(Base):
    def test_folded_description_first_sentence(self):
        cat = catalog.build(router.STATE_DIR, Path(self.skills))
        by = {s["name"]: s for s in cat["skills"]}
        self.assertEqual(by["ponytail"]["desc"], "Does ponytail things.")


class TestShouldRoute(Base):
    def test_modes(self):
        c = self.cfg
        self.assertFalse(router.should_route("fix the header bug now", "off", c))
        self.assertFalse(router.should_route("fix the header bug now", "ask", c))
        self.assertTrue(router.should_route("jev: fix the header bug", "ask", c))
        self.assertTrue(router.should_route("ok", "all", c))
        self.assertFalse(router.should_route("ok", "smart", c))
        self.assertFalse(router.should_route("yes do it", "smart", c))
        self.assertFalse(router.should_route("/caveman lite please now", "all", c))
        self.assertTrue(router.should_route("fix the header bug now", "smart", c))


class TestPrompt(Base):
    def test_mode_command_blocks_and_persists(self):
        out = self.run_hook(router.on_prompt, {"session_id": "s1", "prompt": "jev off"})
        self.assertEqual(out["decision"], "block")
        self.assertEqual(router.load_session("s1", self.cfg)["mode"], "off")

    def test_routes_and_dedupes(self):
        ans = fake_answers(self.cfg, "use-railway", 0.95, gates={"ponytail": 0.9},
                           tools={"railway": 0.9, "figma": 0.01})
        with mock.patch.object(jev, "load_key", return_value="k" * 20), \
             mock.patch.object(jev, "evaluate", return_value=(ans, {"tokens": 1})):
            out = self.run_hook(router.on_prompt, {"session_id": "s2", "prompt": "deploy and fix the build"})
            ctx = out["hookSpecificOutput"]["additionalContext"]
            self.assertIn("`ponytail`", ctx)
            self.assertIn("`use-railway`", ctx)
            self.assertIn("likely needed: railway", ctx)
            self.assertIn("figma", ctx)
            ctx2 = self.run_hook(router.on_prompt, {"session_id": "s2", "prompt": "deploy and fix the build"})["hookSpecificOutput"]["additionalContext"]
            self.assertNotIn("Load skill", ctx2)
            self.assertIn("Already active", ctx2)

    def test_low_confidence_skill_ignored(self):
        ans = fake_answers(self.cfg, "use-railway", 0.2)
        new, _, _, _ = router.decide(ans, self.cfg, [])
        self.assertEqual(new, [])

    def test_failure_falls_back_once(self):
        with mock.patch.object(jev, "load_key", side_effect=jev.JevError("no key")):
            out = self.run_hook(router.on_prompt, {"session_id": "s3", "prompt": "fix the header bug now"})
            self.assertIn("catalog.md", out["hookSpecificOutput"]["additionalContext"])
            self.assertIsNone(self.run_hook(router.on_prompt, {"session_id": "s3", "prompt": "fix the header bug now"}))


class TestSessionStart(Base):
    def test_injects_always_on_and_resets(self):
        router.save_session("s4", {"mode": "all", "loaded": ["ponytail"], "fallback_shown": True})
        out = self.run_hook(router.on_session_start, {"session_id": "s4"})
        self.assertIn("Routing mode: all", out["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(router.load_session("s4", self.cfg)["loaded"], [])
        buf = io.StringIO()
        with redirect_stdout(buf):
            router.on_always_on("caveman", self.cfg)
            router.on_always_on("ponytail", self.cfg)
        lines = buf.getvalue().strip().splitlines()
        self.assertEqual(len(lines), 1)
        ctx = json.loads(lines[0])["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Body of caveman.", ctx)
        self.assertNotIn("name: caveman", ctx)


if __name__ == "__main__":
    unittest.main()
