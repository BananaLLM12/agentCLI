"""OpenAI Chat Completions adapter.

Covers OpenAI itself and every "OpenAI-compatible" service. The only thing
that changes between them is `base_url`, the API key, and occasionally a
custom header — so third-party providers cost us nothing extra.
"""
from __future__ import annotations

import base64
import json
import uuid
from typing import Any, Callable

from ..http import get_json, post_json, stream_sse
from ..types import Completion, Message, ToolCall, ToolSpec
from .base import Provider


class OpenAICompatProvider(Provider):
    name = "openai-compat"

    def _base(self) -> str:
        return (self.base_url or "https://api.openai.com/v1").rstrip("/")

    def _endpoint(self) -> str:
        return f"{self._base()}/chat/completions"

    def list_models(self) -> list[dict]:
        resp = get_json(f"{self._base()}/models",
                        {"Authorization": f"Bearer {self.api_key}", **self.extra_headers})
        out = []
        for m in resp.get("data", []):
            top = m.get("top_provider") or {}   # openrouter exposes real caps here
            out.append({
                "id": m.get("id"),
                "context": m.get("context_length") or m.get("context_window")
                           or top.get("context_length"),
                "max_output": top.get("max_completion_tokens")
                              or m.get("max_output_tokens"),
            })
        return [m for m in out if m["id"]]

    # --- internal model -> OpenAI wire format ---------------------------
    def _encode_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "assistant" and m.tool_calls:
                out.append({
                    "role": "assistant",
                    "content": m.content or None,
                    "tool_calls": [{
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name,
                                     "arguments": json.dumps(tc.arguments)},
                    } for tc in m.tool_calls],
                })
            elif m.role == "tool":
                out.append({
                    "role": "tool",
                    "tool_call_id": m.tool_call_id,
                    "content": m.content,
                })
            elif m.role == "user" and m.images:
                parts: list[dict[str, Any]] = [{"type": "text", "text": m.content}]
                for img in m.images:
                    b64 = base64.b64encode(img.data).decode()
                    parts.append({"type": "image_url",
                                  "image_url": {"url": f"data:{img.mime};base64,{b64}"}})
                out.append({"role": "user", "content": parts})
            else:
                out.append({"role": m.role, "content": m.content})
        return out

    def _encode_tools(self, tools: list[ToolSpec]) -> list[dict[str, Any]]:
        return [{
            "type": "function",
            "function": {"name": t.name, "description": t.description,
                         "parameters": t.parameters},
        } for t in tools]

    # --- request --------------------------------------------------------
    def chat(self, messages, tools, temperature=0.7, max_tokens=1024) -> Completion:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": self._encode_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = self._encode_tools(tools)
            payload["tool_choice"] = "auto"

        headers = {"Authorization": f"Bearer {self.api_key}", **self.extra_headers}
        resp = post_json(self._endpoint(), payload, headers)

        choice = resp["choices"][0]
        msg = choice["message"]
        calls: list[ToolCall] = []
        for tc in msg.get("tool_calls") or []:
            fn = tc["function"]
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {"_raw": fn.get("arguments", "")}
            calls.append(ToolCall(id=tc.get("id") or f"call_{uuid.uuid4().hex[:8]}",
                                  name=fn["name"], arguments=args))

        return Completion(text=msg.get("content") or "", tool_calls=calls,
                          raw=resp, finish_reason=choice.get("finish_reason", ""))

    # --- streaming ------------------------------------------------------
    def stream(self, messages, tools, on_delta, temperature=0.7, max_tokens=1024):
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": self._encode_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = self._encode_tools(tools)
            payload["tool_choice"] = "auto"
        headers = {"Authorization": f"Bearer {self.api_key}", **self.extra_headers}

        text_parts: list[str] = []
        # tool-call fragments arrive keyed by index; stitch them together
        acc: dict[int, dict[str, str]] = {}
        finish = ""
        for event in stream_sse(self._endpoint(), payload, headers):
            choices = event.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta", {})
            if delta.get("content"):
                text_parts.append(delta["content"])
                on_delta(delta["content"])
            for tc in delta.get("tool_calls") or []:
                idx = tc.get("index", 0)
                slot = acc.setdefault(idx, {"id": "", "name": "", "args": ""})
                if tc.get("id"):
                    slot["id"] = tc["id"]
                fn = tc.get("function") or {}
                if fn.get("name"):
                    slot["name"] = fn["name"]
                if fn.get("arguments"):
                    slot["args"] += fn["arguments"]
            if choices[0].get("finish_reason"):
                finish = choices[0]["finish_reason"]

        calls: list[ToolCall] = []
        for idx in sorted(acc):
            slot = acc[idx]
            try:
                args = json.loads(slot["args"] or "{}")
            except json.JSONDecodeError:
                args = {"_raw": slot["args"]}
            calls.append(ToolCall(id=slot["id"] or f"call_{uuid.uuid4().hex[:8]}",
                                  name=slot["name"], arguments=args))

        return Completion(text="".join(text_parts), tool_calls=calls,
                          raw=None, finish_reason=finish)
