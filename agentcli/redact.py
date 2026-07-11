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
    (re.compile(r"ghp_[A-Za-z0-9]{36}"), "github"),
    (re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}"), "slack"),
    (re.compile(r"(?:r8_|hf_|pplx-|tvly-|dsk-)[A-Za-z0-9]{16,}"), "token"),
    (re.compile(r"sk-[A-Za-z0-9]{32,}"), "openai"),   # generic sk- last
]


def _mask(token: str) -> str:
    """Keep a short recognizable prefix, redact the rest."""
    prefix = token[:6] if len(token) > 10 else token[:2]
    return f"{prefix}…[REDACTED]"


def redact(text: str) -> tuple[str, list[str]]:
    """Return (clean_text, [provider labels of what was hidden])."""
    found: list[str] = []

    def sub(label):
        def repl(m):
            found.append(label)
            return _mask(m.group(0))
        return repl

    for rx, label in _PATTERNS:
        text = rx.sub(sub(label), text)
    return text, found
