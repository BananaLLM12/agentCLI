"""Provider interface. Every backend implements `chat`."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable

from ..types import Completion, Message, ToolSpec


class Provider(ABC):
    #: human-readable id, e.g. "openai", "anthropic", "groq"
    name: str = "base"

    def __init__(self, model: str, api_key: str, base_url: str | None = None,
                 extra_headers: dict[str, str] | None = None):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.extra_headers = extra_headers or {}

    @abstractmethod
    def chat(self, messages: list[Message], tools: list[ToolSpec],
             temperature: float = 0.7, max_tokens: int = 1024) -> Completion:
        """One round trip. Returns text and/or tool calls."""
        raise NotImplementedError

    def stream(self, messages: list[Message], tools: list[ToolSpec],
               on_delta: Callable[[str], None],
               temperature: float = 0.7, max_tokens: int = 1024) -> Completion:
        """Stream text deltas through `on_delta`, return the full Completion.

        Default: no real streaming — call `chat` and emit the text in one go.
        Adapters that support SSE override this.
        """
        c = self.chat(messages, tools, temperature, max_tokens)
        if c.text:
            on_delta(c.text)
        return c

    def list_models(self) -> list[dict]:
        """Discover available models. Returns dicts of
        {id, context, max_output} — the latter two may be None if the API
        doesn't report them. Default: not supported.
        """
        return []
