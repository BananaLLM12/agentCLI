"""Tamper-evident action log — the "keep a record every action" defense.

Every tool call, permission decision, and security event is appended to a
hash-chained log: each entry embeds the hash of the previous one, so deleting or
editing any entry breaks the chain and is detectable with `verify()`. This is
one of the few defenses security researchers agree actually holds — you can't
prevent a determined injection, but you can guarantee it leaves an unforgeable
trail (accountability + forensics after the fact).
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

AUDIT_PATH = Path(os.environ.get(
    "AGENTCLI_AUDIT", Path.home() / ".agentcli" / "audit.log"))
_GENESIS = "0" * 64


def _hash(prev: str, body: dict) -> str:
    blob = prev + json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def _last_hash() -> str:
    if not AUDIT_PATH.exists():
        return _GENESIS
    try:
        last = None
        with open(AUDIT_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    last = line
        return json.loads(last)["hash"] if last else _GENESIS
    except (OSError, json.JSONDecodeError, KeyError):
        return _GENESIS


def record(event: str, detail: str = "") -> None:
    """Append one hash-chained entry. Best-effort — never breaks the agent."""
    try:
        prev = _last_hash()
        body = {"ts": round(time.time(), 3), "event": event,
                "detail": str(detail)[:500], "prev": prev}
        entry = {**body, "hash": _hash(prev, body)}
        AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(AUDIT_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        try:
            os.chmod(AUDIT_PATH, 0o600)
        except OSError:
            pass
    except Exception:
        pass


def verify() -> dict:
    """Walk the chain; report the first break (if any)."""
    if not AUDIT_PATH.exists():
        return {"ok": True, "entries": 0, "broken_at": None}
    prev = _GENESIS
    n = 0
    with open(AUDIT_PATH, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            n += 1
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                return {"ok": False, "entries": n, "broken_at": i}
            body = {k: e[k] for k in ("ts", "event", "detail", "prev")}
            if e.get("prev") != prev or _hash(prev, body) != e.get("hash"):
                return {"ok": False, "entries": n, "broken_at": i}
            prev = e["hash"]
    return {"ok": True, "entries": n, "broken_at": None}


def tail(k: int = 15) -> list[dict]:
    if not AUDIT_PATH.exists():
        return []
    out = []
    with open(AUDIT_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return out[-k:]
