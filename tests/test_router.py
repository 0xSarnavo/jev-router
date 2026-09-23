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

import jev  # noqa: E402
import router  # noqa: E402
import skills  # noqa: E402


def noul(p):
    return {"type": "noul", "noul": p}


def fake_answers(cfg, skill="none", p=0.9, gates=None, tool_p=None):
    a = {"skill": {"type": "choice", "choice": skill, "probabilities": {skill: p}, "confidence": p}}
    for g in cfg["skills"]["gated"]:
        a[f"gate:{g}"] = noul((gates or {}).get(g, 0.05))
    for t in cfg["tools"]["groups"]:
        a[f"tool:{t}"] = noul((tool_p or {}).get(t, 0.05))
    return a


class Base(unittest.TestCase):
    def setUp(self):
        self.skills_dir = Path(tempfile.mkdtemp())
        for name in ("ponytail", "caveman", "use-railway", "no-ai-slop", "potpie-cli", "i-have-adhd"):
            (self.skills_dir / name).mkdir()
            (self.skills_dir / name / "SKILL.md").write_text(
                f"---\nname: {name}\ndescription: >\n  Does {name} things. More.\n---\n\nBody of {name}.\n")
        router.STATE_DIR = Path(tempfile.mkdtemp())
        self.patch = mock.patch.object(skills, "SKILLS_DIR", self.skills_dir)
        self.patch.start()
        self.cfg = router.load_config()

    def tearDown(self):
        self.patch.stop()

    def run_hook(self, fn, *args):
        buf = io.StringIO()
        with redirect_stdout(buf):
            fn(*args)
        out = buf.getvalue().strip()
        return [json.loads(line) for line in out.splitlines()] if out else []

    def prompt(self, sid, text, answers=None):
        with mock.patch.object(jev, "load_key", return_value="k" * 20), \
             mock.patch.object(jev, "evaluate", return_value=(answers, {"tokens": 1})) as ev:
            out = self.run_hook(router.on_prompt, {"session_id": sid, "prompt": text}, self.cfg)
        return (out[0] if out else None), ev


class TestSkills(Base):
    def test_folded_description_first_sentence(self):
        cat = skills.build_catalog(router.STATE_DIR)
        self.assertEqual({s["name"]: s["desc"] for s in cat["skills"]}["ponytail"], "Does ponytail things.")

    def test_low_confidence_pick_ignored(self):
        s = {"loaded": []}
        line, _ = skills.route(self.cfg["skills"], fake_answers(self.cfg, "use-railway", 0.2), s, router.STATE_DIR)
        self.assertEqual(s["loaded"], [])
        self.assertIn("No specialised skill", line)


class TestModes(Base):
    def test_should_route(self):
        c = self.cfg
        self.assertFalse(router.should_route("fix the header bug now", "off", c))
        self.assertFalse(router.should_route("fix the header bug now", "ask", c))
        self.assertTrue(router.should_route("jev: fix the header bug", "ask", c))
        self.assertTrue(router.should_route("ok", "all", c))
        self.assertFalse(router.should_route("ok", "smart", c))
        self.assertFalse(router.should_route("yes do it", "smart", c))
        self.assertFalse(router.should_route("/caveman lite please now", "all", c))
        self.assertTrue(router.should_route("fix the header bug now", "smart", c))

    def test_mode_command_blocks_and_persists(self):
        out, ev = self.prompt("s1", "jev off")
        self.assertEqual(out["decision"], "block")
        self.assertEqual(router.load_session("s1", self.cfg)["mode"], "off")
        ev.assert_not_called()

    def test_toggle_router_drops_its_questions(self):
        self.prompt("s5", "jev tools off")
        ans = fake_answers(self.cfg)
        out, ev = self.prompt("s5", "fix the header bug now", ans)
        self.assertFalse(any(k.startswith("tool:") for k in ev.call_args.args[2]))
        self.assertNotIn("Tools", out["hookSpecificOutput"]["additionalContext"])


class TestPrompt(Base):
    def test_routes_and_dedupes(self):
        ans = fake_answers(self.cfg, "use-railway", 0.95, gates={"ponytail": 0.9},
                           tool_p={"railway": 0.9, "figma": 0.01})
        out, _ = self.prompt("s2", "deploy and fix the build", ans)
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("`ponytail`", ctx)
        self.assertIn("`use-railway`", ctx)
        self.assertIn("likely needed: railway", ctx)
        self.assertIn("figma", ctx)
        out, _ = self.prompt("s2", "deploy and fix the build", ans)
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertNotIn("Load skill", ctx)
        self.assertIn("Already active", ctx)

    def test_failure_falls_back_once(self):
        with mock.patch.object(jev, "load_key", side_effect=jev.JevError("no key")):
            out = self.run_hook(router.on_prompt, {"session_id": "s3", "prompt": "fix the header bug now"}, self.cfg)
            self.assertIn("catalog.md", out[0]["hookSpecificOutput"]["additionalContext"])
            self.assertEqual(self.run_hook(router.on_prompt, {"session_id": "s3", "prompt": "fix the header bug now"}, self.cfg), [])


class TestSessionStart(Base):
    def test_resets_and_injects_always_on(self):
        router.save_session("s4", {"mode": "all", "off": [], "loaded": ["ponytail"], "fallback_shown": True})
        out = self.run_hook(router.on_session_start, {"session_id": "s4"}, self.cfg)
        self.assertIn("Mode: all", out[0]["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(router.load_session("s4", self.cfg)["loaded"], [])
        out = self.run_hook(router.on_always_on, "caveman", self.cfg)
        out += self.run_hook(router.on_always_on, "ponytail", self.cfg)
        self.assertEqual(len(out), 1)
        ctx = out[0]["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Body of caveman.", ctx)
        self.assertNotIn("name: caveman", ctx)


if __name__ == "__main__":
    unittest.main()
