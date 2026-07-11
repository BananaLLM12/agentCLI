"""Internal, provider-neutral data model.

Every provider adapter translates its own wire format to and from these
dataclasses, so the agent loop never has to know who it's talking to.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

Role = Literal["system", "user", "assistant", "tool"]


@dataclass
class ToolCall:
    """A model's request to invoke one tool."""
    id: str                      # provider-assigned id, echoed back with the result
    name: str
    arguments: dict[str, Any]    # already JSON-decoded


@dataclass
class Image:
    """An image attached to a user message (for vision-capable models)."""
    data: bytes           # raw image bytes
    mime: str             # e.g. "image/png"


@dataclass
class Message:
    role: Role
    content: str = ""
    # assistant turns may carry tool calls instead of (or besides) text
    tool_calls: list[ToolCall] = field(default_factory=list)
    # tool turns carry the result of a single call
    tool_call_id: Optional[str] = None
    name: Optional[str] = None   # tool name, for tool-role messages
    # user turns may carry images for vision models
    images: list["Image"] = field(default_factory=list)


@dataclass
class ToolSpec:
    """A tool the model is allowed to call, described JSON-Schema style."""
    name: str
    description: str
    parameters: dict[str, Any]   # JSON Schema object


@dataclass
class Completion:
    """What a provider hands back for one turn."""
    text: str
    tool_calls: list[ToolCall]
    raw: Any = None              # untouched provider response, for debugging
    finish_reason: str = ""
