"""Build the skill catalog Jev chooses from, plus a markdown index for fallback."""
import json
import re
from pathlib import Path

SKILLS_DIR = Path.home() / ".claude" / "skills"


def _description(text):
    m = re.match(r"---\s*\n(.*?)\n---", text, re.S)
    if not m:
        return ""
    fm = m.group(1)
    d = re.search(r"^description:[ \t]*(.*?)(?=^\S[\w-]*:|\Z)", fm, re.S | re.M)
    if not d:
        return ""
    desc = " ".join(d.group(1).split()).lstrip(">|").strip().strip("'\"")
    return re.split(r"(?<=[.!?])\s", desc)[0][:160]


def scan(skills_dir=SKILLS_DIR):
    skills = []
    for f in sorted(Path(skills_dir).glob("*/SKILL.md")):
        name = f.parent.name
        skills.append({"name": name, "desc": _description(f.read_text(errors="ignore")),
                       "path": str(f)})
    return skills


def newest_mtime(skills_dir=SKILLS_DIR):
    files = list(Path(skills_dir).glob("*/SKILL.md"))
    return max((f.stat().st_mtime for f in files), default=0) + len(files)


def build(out_dir, skills_dir=SKILLS_DIR):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    skills = scan(skills_dir)
    cat = {"stamp": newest_mtime(skills_dir), "skills": skills}
    (out_dir / "catalog.json").write_text(json.dumps(cat, indent=1))
    lines = ["# Skill index", "", "Read the file of the best match and follow it.", ""]
    lines += [f"- `{s['name']}`: {s['desc']} ({s['path']})" for s in skills]
    (out_dir / "catalog.md").write_text("\n".join(lines) + "\n")
    return cat


def load(out_dir, skills_dir=SKILLS_DIR):
    p = Path(out_dir) / "catalog.json"
    if p.exists():
        cat = json.loads(p.read_text())
        if cat.get("stamp") == newest_mtime(skills_dir):
            return cat
    return build(out_dir, skills_dir)


if __name__ == "__main__":
    from router import STATE_DIR
    print(len(build(STATE_DIR)["skills"]), "skills indexed")
