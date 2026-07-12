"""Anthropic Messages API adapter."""
from __future__ import annotations

import base64
import json
from typing import Any, Callable

from ..http import get_json, post_json, stream_sse
from ..types import Completion, Message, ToolCall, ToolSpec
from .base import Provider


class AnthropicProvider(Provider):
    name = "anthropic"
    api_version = "2023-06-01"

    def _base(self) -> str:
        return (self.base_url or "https://api.anthropic.com").rstrip("/")

    def _endpoint(self) -> str:
        return f"{self._base()}/v1/messages"

    def list_models(self) -> list[dict]:
        resp = get_json(f"{self._base()}/v1/models",
                        {"x-api-key": self.api_key,
                         "anthropic-version": self.api_version, **self.extra_headers})
        # Anthropic doesn't report token caps here; leave them for the table
        return [{"id": m.get("id"), "context": None, "max_output": None}
                for m in resp.get("data", []) if m.get("id")]

    def _encode(self, messages: list[Message]) -> tuple[str, list[dict[str, Any]]]:
        system_parts: list[str] = []
        out: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "system":
                system_parts.append(m.content)
            elif m.role == "assistant" and m.tool_calls:
                blocks: list[dict[str, Any]] = []
                if m.content:
                    blocks.append({"type": "text", "text": m.content})
                for tc in m.tool_calls:
                    blocks.append({"type": "tool_use", "id": tc.id,
                                   "name": tc.name, "input": tc.arguments})
                out.append({"role": "assistant", "content": blocks})
            elif m.role == "tool":
                blocks = [{"type": "tool_result",
                           "tool_use_id": m.tool_call_id,
                           "content": m.content}]
                for img in m.images:      # image blocks share the tool_result turn
                    blocks.append({"type": "image", "source": {
                        "type": "base64", "media_type": img.mime,
                        "data": base64.b64encode(img.data).decode()}})
                out.append({"role": "user", "content": blocks})
            elif m.role == "user" and m.images:
                blocks: list[dict[str, Any]] = []
                for img in m.images:
                    blocks.append({"type": "image", "source": {
                        "type": "base64", "media_type": img.mime,
                        "data": base64.b64encode(img.data).decode()}})
                if m.content:
                    blocks.append({"type": "text", "text": m.content})
                out.append({"role": "user", "content": blocks})
            else:
                out.append({"role": m.role, "content": m.content})
        return "\n\n".join(system_parts), out

    def chat(self, messages, tools, temperature=0.7, max_tokens=1024) -> Completion:
        system, msgs = self._encode(messages)
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": msgs,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = [{"name": t.name, "description": t.description,
                                 "input_schema": t.parameters} for t in tools]

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": self.api_version,
            **self.extra_headers,
        }
        resp = post_json(self._endpoint(), payload, headers)

        text_parts, calls = [], []
        for block in resp.get("content", []):
            if block["type"] == "text":
                text_parts.append(block["text"])
            elif block["type"] == "tool_use":
                calls.append(ToolCall(id=block["id"], name=block["name"],
                                      arguments=block.get("input", {})))

        return Completion(text="".join(text_parts), tool_calls=calls,
                          raw=resp, finish_reason=resp.get("stop_reason", ""))

    # --- streaming ------------------------------------------------------
    def stream(self, messages, tools, on_delta, temperature=0.7, max_tokens=1024):
        system, msgs = self._encode(messages)
        payload: dict[str, Any] = {
            "model": self.model, "messages": msgs,
            "temperature": temperature, "max_tokens": max_tokens,
        }
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = [{"name": t.name, "description": t.description,
                                 "input_schema": t.parameters} for t in tools]
        headers = {"x-api-key": self.api_key,
                   "anthropic-version": self.api_version, **self.extra_headers}

        text_parts: list[str] = []
        # blocks keyed by index; tool_use blocks accumulate partial JSON
        blocks: dict[int, dict[str, str]] = {}
        finish = ""
        for ev in stream_sse(self._endpoint(), payload, headers):
            etype = ev.get("type")
            if etype == "content_block_start":
                idx = ev["index"]
                cb = ev["content_block"]
                if cb["type"] == "tool_use":
                    blocks[idx] = {"kind": "tool", "id": cb["id"],
                                   "name": cb["name"], "args": ""}
                else:
                    blocks[idx] = {"kind": "text"}
            elif etype == "content_block_delta":
                d = ev["delta"]
                if d["type"] == "text_delta":
                    text_parts.append(d["text"])
                    on_delta(d["text"])
                elif d["type"] == "input_json_delta":
                    blocks.setdefault(ev["index"], {"kind": "tool", "id": "",
                                                    "name": "", "args": ""})
                    blocks[ev["index"]]["args"] += d.get("partial_json", "")
            elif etype == "message_delta":
                finish = ev.get("delta", {}).get("stop_reason", finish)

        calls: list[ToolCall] = []
        for idx in sorted(blocks):
            b = blocks[idx]
            if b.get("kind") != "tool":
                continue
            try:
                args = json.loads(b["args"] or "{}")
            except json.JSONDecodeError:
                args = {"_raw": b["args"]}
            calls.append(ToolCall(id=b["id"], name=b["name"], arguments=args))

        return Completion(text="".join(text_parts), tool_calls=calls,
                          raw=None, finish_reason=finish)
