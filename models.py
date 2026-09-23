"""Model router: rate how much model a prompt needs and pick model and effort per harness."""
import hashlib
import json
from pathlib import Path

TIERS = ("small", "standard", "large", "hard")


def questions(cfg, ctx):
    return {
        "model:effort": {
            "type": "score",
            "instructions": "How much reasoning does the coding assistant need to do the request "
                            "in `prompt` well?",
            "criteria": [
                "A lookup, a factual question, or a one-line change.",
                "A small change in one file, or a short explanation of existing code.",
                "A normal feature, bug fix or refactor touching a few files.",
                "A multi-file design, a tricky bug with unclear cause, or careful debugging.",
                "Open-ended architecture, research or a long autonomous task with many steps.",
            ],
        },
        "model:risk": {"type": "noul",
                       "instructions": "Would a wrong result for `prompt` be costly: data loss, "
                                       "security, production systems, payments or migrations?"},
        "model:context": {"type": "noul",
                          "instructions": "Does `prompt` need a very large amount of code, logs or "
                                          "documents in view at once, far beyond a few files?"},
    }


def tier(cfg, answers):
    s = answers["model:effort"]["score"]
    t = 0 if s < 1.5 else 1 if s < 2.5 else 2 if s < 3.5 else 3
    if answers["model:risk"]["noul"] >= cfg["risk_threshold"]:
        t = max(t, 2)
    name = TIERS[t]
    if name != "small" and answers["model:context"]["noul"] >= cfg["context_threshold"]:
        name = "long"
    return name, round(s, 2)


def pick(cfg, harness, name):
    model, effort = cfg["tiers"][harness][name]
    return model, effort


def rank(cfg, harness, model):
    for i, family in enumerate(cfg["rank"].get(harness, [])):
        if family in (model or "").lower():
            return i
    return None


def claude_model(data):
    """Claude Code does not pass the model to hooks. Read it from the transcript, then settings."""
    try:
        for line in reversed(Path(data["transcript_path"]).read_text().splitlines()[-200:]):
            if '"model"' in line:
                m = (json.loads(line).get("message") or {}).get("model")
                if m and m != "<synthetic>":
                    return m
    except (OSError, KeyError, ValueError, TypeError):
        pass
    try:
        return json.loads((Path.home() / ".claude" / "settings.json").read_text()).get("model")
    except (OSError, ValueError):
        return None


def harness_of(data):
    if data.get("harness") == "opencode":
        return "opencode"
    return "codex" if "/.codex/" in (data.get("transcript_path") or "") else "claude"


def meta_backend(ctx):
    return ctx.get("backend")


def label(model, effort):
    return f"{model} at {effort} effort" if effort else model


def route(cfg, answers, session, ctx):
    data, prompt, harness = ctx["data"], ctx["prompt"], ctx["harness"]
    current = data.get("model") or (claude_model(data) if harness == "claude" else None)
    name, score = tier(cfg, answers)
    model, effort = pick(cfg, harness, name)
    detail = {"tier": name, "score": score, "current": current, "pick": model, "effort": effort}
    mode = session.get("model_mode", cfg["mode"])
    if meta_backend(ctx) == "laya" and mode in ("ask", "auto"):
        mode = "suggest"
    try:
        long_session = Path(data.get("transcript_path") or "").stat().st_size > cfg["quiet_after_kb"] * 1024
    except OSError:
        long_session = False
    if harness == "opencode":
        if mode in ("ask", "auto") and current and model != current:
            detail["switch"] = model
        return "", detail
    cur_r, new_r = rank(cfg, harness, current), rank(cfg, harness, model)
    if mode == "off" or cur_r is None or new_r is None or cur_r == new_r:
        return "", detail
    rec = label(model, effort)
    if long_session and new_r < cur_r:
        detail["quiet"] = "long session"
        return "", detail
    if new_r > cur_r:
        return (f"Model: Jev rates this {name} (effort {score}/4). {rec} may do better than "
                f"{current}. Say so in one line at the top of your reply."), detail
    if mode == "suggest" or session.get("model_asked") == name:
        return (f"Model: Jev rates this {name} (effort {score}/4). {rec} would do. Mention it "
                "in one line at the top of your reply."), detail
    session["model_asked"] = name
    if harness == "codex":
        digest = hashlib.sha256(prompt.encode()).hexdigest()[:12]
        if session.get("model_blocked") == digest:
            return "", detail
        session["model_blocked"] = digest
        detail["block"] = (f"Jev rates this {name} (effort {score}/4). Run /model and pick {rec}, "
                           f"then resend. Resend unchanged to keep {current}.")
        return "", detail
    sub = cfg["claude_subagent"].get(name)
    if mode == "auto" and sub:
        return (f"Model: Jev rates this {name}. Do the whole task in one subagent via the Agent "
                f"tool with model '{sub}', then pass its result back briefly."), detail
    options = f"'{rec} (Recommended)'" + (
        f": you then do the whole task in one subagent via the Agent tool with model '{sub}'"
        if sub else ": the user switches with /model") + f"; 'Keep {current}': you do it yourself"
    return (f"Model: Jev rates this {name} (effort {score}/4). Before starting, ask the user with "
            f"AskUserQuestion, header 'Model', options {options}. Then follow their choice."), detail
