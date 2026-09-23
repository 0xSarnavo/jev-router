"""Skill router: load skills on demand instead of listing them all at startup."""
import json
import re
from pathlib import Path

SKILLS_DIR = Path.home() / ".claude" / "skills"


def _description(text):
    m = re.match(r"---\s*\n(.*?)\n---", text, re.S)
    d = m and re.search(r"^description:[ \t]*(.*?)(?=^\S[\w-]*:|\Z)", m.group(1), re.S | re.M)
    if not d:
        return ""
    desc = " ".join(d.group(1).split()).lstrip(">|").strip().strip("'\"")
    return re.split(r"(?<=[.!?])\s", desc)[0][:160]


def _stamp(skills_dir):
    files = list(Path(skills_dir).glob("*/SKILL.md"))
    return max((f.stat().st_mtime for f in files), default=0) + len(files)


def build_catalog(state_dir, skills_dir=None):
    skills_dir = skills_dir or SKILLS_DIR
    skills = [{"name": f.parent.name, "desc": _description(f.read_text(errors="ignore")),
               "path": str(f)} for f in sorted(Path(skills_dir).glob("*/SKILL.md"))]
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    cat = {"stamp": _stamp(skills_dir), "skills": skills}
    (state_dir / "catalog.json").write_text(json.dumps(cat, indent=1))
    lines = ["# Skill index", "", "Read the file of the best match and follow it.", ""]
    lines += [f"- `{s['name']}`: {s['desc']} ({s['path']})" for s in skills]
    (state_dir / "catalog.md").write_text("\n".join(lines) + "\n")
    return cat


def load_catalog(state_dir, skills_dir=None):
    p = Path(state_dir) / "catalog.json"
    if p.exists():
        cat = json.loads(p.read_text())
        if cat.get("stamp") == _stamp(skills_dir or SKILLS_DIR):
            return cat
    return build_catalog(state_dir, skills_dir)


def paths(state_dir):
    return {s["name"]: s["path"] for s in load_catalog(state_dir)["skills"]}


def body(path):
    text = Path(path).read_text(errors="ignore")
    return re.sub(r"\A---\s*\n.*?\n---\s*\n", "", text, count=1, flags=re.S).strip()


def questions(cfg, ctx):
    skip = set(cfg["always_on"]) | set(cfg["gated"]) | set(cfg["never_route"])
    options = {s["name"]: s["desc"] or None
               for s in load_catalog(ctx["state_dir"])["skills"] if s["name"] not in skip}
    options["none"] = "No specialised skill fits. The assistant can answer or do this directly."
    q = {"skill": {"type": "choice", "criteria": options,
                   "instructions": "Which specialised skill, if any, clearly matches the request "
                                   "in `prompt`? Choose none unless one directly fits the task."}}
    for name, question in cfg["gated"].items():
        q[f"gate:{name}"] = {"type": "noul", "instructions": question}
    return q


def route(cfg, answers, session, ctx):
    picks = [n for n in cfg["gated"] if answers[f"gate:{n}"]["noul"] >= cfg["gate_threshold"]]
    sk = answers["skill"]
    p = sk["probabilities"].get(sk["choice"], 0)
    if sk["choice"] != "none" and p >= cfg["pick_threshold"]:
        picks.append(sk["choice"])
    known = paths(ctx["state_dir"])
    new = [n for n in picks if n not in session["loaded"] and n in known]
    active = [n for n in picks if n in session["loaded"]]
    session["loaded"] += new
    parts = [f"Load skill `{n}`: read {known[n]} and follow it for this task." for n in new]
    if active:
        parts.append("Already active this session: " + ", ".join(active) + ".")
    if not picks:
        parts.append("No specialised skill needed.")
    return " ".join(parts), {"new": new, "active": active, "choice": sk["choice"],
                             "choice_p": round(p, 3)}
