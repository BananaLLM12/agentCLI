"""Auto-redaction of secrets pasted into the chat.

If you paste an API key, it gets masked before it's sent to the model, written
to disk, or echoed — so a stray copy/paste never leaks a credential. Detection
is pattern-based over the common key formats; unknown-but-obvious long tokens
are left alone to avoid false positives on normal text.
"""
from __future__ import annotations

import re

# (compiled pattern, provider label). Ordered most-specific first.
_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"), "anthropic"),
    (re.compile(r"sk-proj-[A-Za-z0-9_\-]{20,}"), "openai"),
    (re.compile(r"sk-or-v1-[A-Za-z0-9]{20,}"), "openrouter"),
    (re.compile(r"gsk_[A-Za-z0-9]{20,}"), "groq"),
    (re.compile(r"AIza[A-Za-z0-9_\-]{30,}"), "google"),
    (re.compile(r"xai-[A-Za-z0-9]{20,}"), "xai"),
    (re.compile(r"AKIA[A-Z0-9]{16}"), "aws"),
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"), "github"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), "github"),
    (re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}"), "slack"),
    (re.compile(r"(?:r8_|hf_|pplx-|tvly-|dsk-|co_|key-)[A-Za-z0-9]{16,}"), "token"),
    (re.compile(r"sk-[A-Za-z0-9]{32,}"), "openai"),   # generic sk- last
    # a "key = <long opaque token>" assignment, whatever the format
    (re.compile(r"(?i)(?:api[_-]?key|secret|token|bearer|password)"
                r"['\"\s:=]+([A-Za-z0-9_\-]{20,})"), "assignment"),
]


def _mask(token: str) -> str:
    """Keep a short recognizable prefix, redact the rest."""
    prefix = token[:6] if len(token) > 10 else token[:2]
    return f"{prefix}…[REDACTED]"


_KEYS_CACHE: set[str] | None = None


def invalidate_cache() -> None:
    global _KEYS_CACHE
    _KEYS_CACHE = None


def _known_keys() -> set[str]:
    """Every API key this install has configured — from config.json, the OS
    keychain, and known env vars. These are redacted by EXACT match, so any key
    format is caught regardless of whether a regex knows its shape. Cached to
    avoid a keychain subprocess on every call (invalidate on key changes)."""
    global _KEYS_CACHE
    if _KEYS_CACHE is not None:
        return _KEYS_CACHE
    keys: set[str] = set()
    try:
        from . import config
        cfg = config.load()
        for v in cfg.get("keys", {}).values():
            if v and v != "<in keychain>":
                keys.add(v)
        if cfg.get("tavily_key"):
            keys.add(cfg["tavily_key"])
        from . import secure_store
        if secure_store.available():
            for pid in list(cfg.get("keys", {})) + ["tavily", "policy_hmac"]:
                v = secure_store.get_key(pid)
                if v:
                    keys.add(v)
    except Exception:
        pass
    import os
    for e in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY",
              "GROQ_API_KEY", "OPENROUTER_API_KEY", "TOGETHER_API_KEY",
              "DEEPSEEK_API_KEY", "MISTRAL_API_KEY", "XAI_API_KEY",
              "FIREWORKS_API_KEY", "PERPLEXITY_API_KEY", "TAVILY_API_KEY"):
        v = os.environ.get(e)
        if v:
            keys.add(v)
    _KEYS_CACHE = {k for k in keys if len(k) >= 12}
    return _KEYS_CACHE


def redact(text: str) -> tuple[str, list[str]]:
    """Return (clean_text, [labels of what was hidden])."""
    found: list[str] = []

    # 1) exact match of THIS install's configured keys — any format, no guessing
    for k in sorted(_known_keys(), key=len, reverse=True):
        if k in text:
            text = text.replace(k, _mask(k))
            found.append("configured-key")

    # 2) pattern-based, for keys not (yet) in the config
    def sub(label):
        def repl(m):
            token = m.group(1) if m.lastindex else m.group(0)
            found.append(label)
            return m.group(0).replace(token, _mask(token))
        return repl

    for rx, label in _PATTERNS:
        text = rx.sub(sub(label), text)
    return text, found
