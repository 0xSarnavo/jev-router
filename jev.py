"""Minimal TypeSafe System One client. Stdlib only, never echoes the key."""
import json
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


def load_key(env_file=None):
    key = os.environ.get("TYPESAFE_API_KEY", "")
    if not key and env_file and os.path.exists(os.path.expanduser(env_file)):
        for line in open(os.path.expanduser(env_file)):
            if line.startswith("TYPESAFE_API_KEY="):
                key = line.split("=", 1)[1].strip().strip("'\"")
    if not KEY_RE.fullmatch(key):
        raise JevError("TYPESAFE_API_KEY is missing or malformed")
    return key


def evaluate(key, state, questions, model="jev-latest", timeout=6):
    body = json.dumps({"state": state, "model": model, "questions": questions}).encode()
    req = urllib.request.Request(URL, body, {
        "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
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
            raise JevError(f"TypeSafe returned HTTP {e.code}") from None
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
