"""Model discovery + token-limit resolution.

Providers rarely report their *output* token cap (Google is the exception).
So we resolve a model's max output tokens as:
    discovered value  >  substring match in LIMITS  >  DEFAULT
The agent's auto-grow covers any under-estimate; this just gives a sane,
usually-maximal starting budget so a single file write isn't truncated.
"""
from __future__ import annotations

# substring -> known max OUTPUT tokens. Ordered longest/most-specific first.
LIMITS: list[tuple[str, int]] = [
    ("gpt-4o-mini", 16384),
    ("gpt-4o", 16384),
    ("gpt-4.1", 32768),
    ("o3", 100000),
    ("o1", 100000),
    ("gpt-4-turbo", 4096),
    ("gpt-3.5", 4096),
    ("claude-3-5", 8192),
    ("claude-3-7", 8192),
    ("claude-sonnet-4", 8192),
    ("claude-opus-4", 8192),
    ("claude-3-opus", 4096),
    ("claude-3-haiku", 4096),
    ("claude", 8192),
    ("llama-3.3", 8192),
    ("llama-3.1", 8192),
    ("llama", 8192),
    ("deepseek", 8192),
    ("mixtral", 8192),
    ("mistral", 8192),
    ("qwen", 8192),
    ("gemini-1.5", 8192),
    ("gemini-2", 8192),
    ("grok", 8192),
]
DEFAULT_MAX_OUTPUT = 8192
HARD_CEILING = 32768   # never request more than this even if a model claims more


def resolve_max_output(model: str, discovered: dict | None = None) -> int:
    """Best-known max output-token budget for `model`."""
    if discovered and discovered.get("max_output"):
        return min(int(discovered["max_output"]), HARD_CEILING)
    m = (model or "").lower()
    for pat, val in LIMITS:
        if pat in m:
            return val
    return DEFAULT_MAX_OUTPUT


# model ids that are chat-capable-looking (filters embeddings, tts, whisper…)
_SKIP = ("embed", "embedding", "whisper", "tts", "moderation", "rerank",
         "guard", "vision-only", "image", "dall-e", "clip", "audio")


def rank_latest(models: list[dict], limit: int = 8) -> list[dict]:
    """Filter to plausible chat models and surface the most useful ones first.

    Preference order roughly tracks capability keywords, so the newest flagship
    families float to the top of the picker.
    """
    def keep(mid: str) -> bool:
        low = mid.lower()
        return not any(s in low for s in _SKIP)

    chat = [m for m in models if m.get("id") and keep(m["id"])]

    priority = ("gpt-4.1", "gpt-4o", "o3", "o1", "claude-sonnet-4", "claude-opus-4",
                "claude-3-7", "claude-3-5", "gemini-2", "llama-3.3", "deepseek",
                "grok", "mixtral", "qwen")

    def score(m: dict) -> tuple:
        low = m["id"].lower()
        for i, p in enumerate(priority):
            if p in low:
                return (0, i, low)
        return (1, 0, low)

    chat.sort(key=score)
    return chat[:limit]
