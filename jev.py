"""Minimal TypeSafe System One client. Stdlib only, never echoes the key."""
import json
import math
import os
import re
import time
import urllib.error
import urllib.request

URL = "https://api.typesafe.ai/v1/systemone"
KEY_RE = re.compile(r"[A-Za-z0-9_.\-]{8,200}")
RETRY_STATUSES = (429, 529)


class JevError(RuntimeError):
    pass


KEY_FILE = os.path.expanduser("~/.config/jev-router/key")
KEY_URL = "https://console.typesafe.ai/keys"


class MissingKey(JevError):
    pass


def load_key(env_file=None):
    """TYPESAFE_API_KEY from the environment, then an optional .env file, then KEY_FILE."""
    key = os.environ.get("TYPESAFE_API_KEY", "")
    if not key and env_file and os.path.exists(os.path.expanduser(env_file)):
        for line in open(os.path.expanduser(env_file)):
            if line.startswith("TYPESAFE_API_KEY="):
                key = line.split("=", 1)[1].strip().strip("'\"")
    if not key and os.path.exists(KEY_FILE):
        key = open(KEY_FILE).read().strip()
    if not KEY_RE.fullmatch(key):
        raise MissingKey("TYPESAFE_API_KEY is missing or malformed")
    return key


def save_key(key):
    if not KEY_RE.fullmatch(key):
        raise MissingKey("that does not look like a TypeSafe API key")
    os.makedirs(os.path.dirname(KEY_FILE), exist_ok=True)
    fd = os.open(KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(key)


def evaluate(key, state, questions, model="jev-latest", timeout=6, url=URL):
    body = json.dumps({"state": state, "model": model, "questions": questions}).encode()
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(url, body, headers)
    t0 = time.time()
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                out = json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            if e.code in RETRY_STATUSES and attempt == 0:
                time.sleep(0.5)
                continue
            raise JevError(f"{url.split('/')[2]} returned HTTP {e.code}") from None
        except Exception as e:
            raise JevError(f"TypeSafe request failed ({type(e).__name__})") from None
    answers = out.get("answers") or {}
    missing = [k for k in questions if k not in answers]
    if missing:
        raise JevError(f"no answer for: {', '.join(sorted(missing))}")
    usage = out.get("usage") or {}
    return answers, {
        "model": out.get("model"),
        "tokens": int(usage.get("input_tokens", 0)) + int(usage.get("output_tokens", 0)),
        "latency_ms": round((time.time() - t0) * 1000),
    }


def laya_fits(question, max_options):
    """Laya degrades past about 20 choice options, so bigger choices stay on Jev."""
    return question["type"] != "choice" or len(question["criteria"]) <= max_options


def ask(cfg, state, questions, backend=None):
    """Send questions to the configured backend: jev, laya, or auto (Jev, then Laya on failure)."""
    backend = backend or cfg["backend"]
    laya = cfg["laya"]
    if backend in ("jev", "auto"):
        try:
            answers, meta = evaluate(load_key(cfg.get("env_file")), state, questions,
                                     cfg["model"], cfg["timeout_s"])
            return answers, {**meta, "backend": "jev"}
        except JevError:
            if backend == "jev":
                raise
    small = {k: q for k, q in questions.items() if laya_fits(q, laya["max_options"])}
    if not small:
        raise JevError("no questions fit Laya")
    answers, meta = evaluate(None, state, small, laya["model"], laya["timeout_s"], laya["url"])
    return calibrate(answers, laya.get("calibration", "")), {**meta, "backend": "laya"}


def calibrate(answers, path):
    """Apply a per-question calibration file to Laya's answers, if one exists."""
    try:
        cal = json.loads(open(os.path.expanduser(path)).read())
    except (OSError, ValueError):
        return answers
    for k, a in answers.items():
        if a["type"] == "noul" and k in cal["noul"]:
            p = min(max(a["noul"], 1e-4), 1 - 1e-4)
            x, (s, b) = math.log(p / (1 - p)), cal["noul"][k]
            a["noul"] = 1 / (1 + math.exp(-(s * x + b)))
        elif a["type"] == "score" and k == "model:effort" and cal.get("effort"):
            probs = [a["probabilities"][str(i)] for i in range(len(a["probabilities"]))] + [1.0]
            a["score"] = min(4.0, max(0.0, sum(x * w for x, w in zip(probs, cal["effort"]))))
    return answers
