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
import mcps  # noqa: E402
import models  # noqa: E402
import router  # noqa: E402
import skills  # noqa: E402


def noul(p):
    return {"type": "noul", "noul": p}


def fake_answers(cfg, skill="none", p=0.9, gates=None, tool_p=None, effort=2.0, mcp_p=None):
    a = {"skill": {"type": "choice", "choice": skill, "probabilities": {skill: p}, "confidence": p},
         "model:effort": {"type": "score", "score": effort},
         "model:risk": noul(0.05), "model:context": noul(0.05)}
    for n, v in (mcp_p or {"railway": 0.05}).items():
        a[f"mcp:{n}"] = noul(v)
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
        self.mcp = mock.patch.object(mcps, "servers", lambda h, cwd=None: {"railway": {}})
        self.mcp.start()
        self.cm = mock.patch.object(models, "claude_model", return_value=None)
        self.cm.start()
        self.cfg = router.load_config()

    def tearDown(self):
        self.patch.stop()
        self.mcp.stop()
        self.cm.stop()

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
        line, _ = skills.route(self.cfg["skills"], fake_answers(self.cfg, "use-railway", 0.2), s,
                               {"state_dir": router.STATE_DIR})
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
                           tool_p={"web": 0.9}, mcp_p={"railway": 0.9})
        out, _ = self.prompt("s2", "deploy and fix the build", ans)
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("`ponytail`", ctx)
        self.assertIn("`use-railway`", ctx)
        self.assertIn("Tools likely needed: web", ctx)
        self.assertIn("MCP servers likely needed: railway", ctx)
        out, _ = self.prompt("s2", "deploy and fix the build", ans)
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertNotIn("Load skill", ctx)
        self.assertIn("Already active", ctx)

    def test_notifications_are_not_routed(self):
        self.assertFalse(router.should_route("<task-notification> done", "all", self.cfg))

    def test_failure_falls_back_once(self):
        with mock.patch.object(jev, "load_key", side_effect=jev.JevError("no key")):
            out = self.run_hook(router.on_prompt, {"session_id": "s3", "prompt": "fix the header bug now"}, self.cfg)
            self.assertIn("catalog.md", out[0]["hookSpecificOutput"]["additionalContext"])
            self.assertEqual(self.run_hook(router.on_prompt, {"session_id": "s3", "prompt": "fix the header bug now"}, self.cfg), [])


class TestModels(Base):
    def ctx(self, harness="claude", model="claude-opus-5-5"):
        data = {"model": model} if harness == "codex" else {}
        if harness == "codex":
            data["transcript_path"] = "/x/.codex/sessions/a.jsonl"
        return {"data": data, "prompt": "p", "harness": harness}

    def test_tiers(self):
        c = self.cfg["models"]
        self.assertEqual(models.tier(c, fake_answers(self.cfg, effort=0.4))[0], "small")
        self.assertEqual(models.tier(c, fake_answers(self.cfg, effort=3.8))[0], "hard")
        risky = fake_answers(self.cfg, effort=0.4)
        risky["model:risk"] = noul(0.9)
        self.assertEqual(models.tier(c, risky)[0], "large")

    def test_claude_ask_uses_selector_once_per_tier(self):
        c, s = self.cfg["models"], {}
        self.cm.stop()
        with mock.patch.object(models, "claude_model", return_value="claude-opus-5-5"):
            line, d = models.route(c, fake_answers(self.cfg, effort=0.4), s, self.ctx())
            self.assertIn("AskUserQuestion", line)
            self.assertIn("model 'haiku'", line)
            line, _ = models.route(c, fake_answers(self.cfg, effort=0.4), s, self.ctx())
            self.assertNotIn("AskUserQuestion", line)
            line, _ = models.route(c, fake_answers(self.cfg, effort=3.8), s, self.ctx())
            self.assertEqual(line, "")

    def test_codex_ask_blocks_then_lets_resend_through(self):
        c, s = self.cfg["models"], {}
        _, d = models.route(c, fake_answers(self.cfg, effort=0.4), s, self.ctx("codex", "gpt-6-sol"))
        self.assertIn("gpt-6-luna at low effort", d["block"])
        s.pop("model_asked")
        _, d = models.route(c, fake_answers(self.cfg, effort=0.4), s, self.ctx("codex", "gpt-6-sol"))
        self.assertNotIn("block", d)

    def test_upgrade_is_only_suggested(self):
        self.cm.stop()
        with mock.patch.object(models, "claude_model", return_value="claude-haiku-4-5"):
            line, _ = models.route(self.cfg["models"], fake_answers(self.cfg, effort=3.8), {}, self.ctx())
        self.assertIn("may do better", line)


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
