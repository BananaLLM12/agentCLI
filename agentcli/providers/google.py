"""Google Gemini (generativelanguage) adapter."""
from __future__ import annotations

import base64
import uuid
from typing import Any

from ..http import get_json, post_json
from ..types import Completion, Message, ToolCall, ToolSpec
from .base import Provider


class GoogleProvider(Provider):
    name = "google"

    def _endpoint(self) -> str:
        base = (self.base_url or "https://generativelanguage.googleapis.com").rstrip("/")
        # key travels as a query param for this API
        return f"{base}/v1beta/models/{self.model}:generateContent?key={self.api_key}"

    def _apibase(self) -> str:
        return (self.base_url or "https://generativelanguage.googleapis.com").rstrip("/")

    def list_models(self) -> list[dict]:
        resp = get_json(f"{self._apibase()}/v1beta/models?key={self.api_key}",
                        dict(self.extra_headers))
        out = []
        for m in resp.get("models", []):
            methods = m.get("supportedGenerationMethods", [])
            if "generateContent" not in methods:
                continue                       # skip embedding-only models
            out.append({
                "id": m.get("name", "").replace("models/", ""),
                "context": m.get("inputTokenLimit"),
                "max_output": m.get("outputTokenLimit"),   # google reports this!
            })
        return [m for m in out if m["id"]]

    def _role(self, role: str) -> str:
        return "model" if role == "assistant" else "user"

    def _encode(self, messages: list[Message]) -> tuple[dict | None, list[dict[str, Any]]]:
        system = None
        contents: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "system":
                system = {"parts": [{"text": m.content}]}
            elif m.role == "assistant" and m.tool_calls:
                parts = [{"functionCall": {"name": tc.name, "args": tc.arguments}}
                         for tc in m.tool_calls]
                if m.content:
                    parts.insert(0, {"text": m.content})
                contents.append({"role": "model", "parts": parts})
            elif m.role == "tool":
                parts = [{"functionResponse": {"name": m.name or "tool",
                                               "response": {"result": m.content}}}]
                for img in m.images:      # inlineData shares the functionResponse turn
                    parts.append({"inlineData": {
                        "mimeType": img.mime,
                        "data": base64.b64encode(img.data).decode()}})
                contents.append({"role": "user", "parts": parts})
            elif m.role == "user" and m.images:
                parts = [{"text": m.content}] if m.content else []
                for img in m.images:
                    parts.append({"inlineData": {
                        "mimeType": img.mime,
                        "data": base64.b64encode(img.data).decode()}})
                contents.append({"role": "user", "parts": parts})
            else:
                contents.append({"role": self._role(m.role),
                                 "parts": [{"text": m.content}]})
        return system, contents

    def chat(self, messages, tools, temperature=0.7, max_tokens=1024) -> Completion:
        system, contents = self._encode(messages)
        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {"temperature": temperature,
                                 "maxOutputTokens": max_tokens},
        }
        if system:
            payload["systemInstruction"] = system
        if tools:
            payload["tools"] = [{"functionDeclarations": [
                {"name": t.name, "description": t.description, "parameters": t.parameters}
                for t in tools]}]

        headers = dict(self.extra_headers)
        resp = post_json(self._endpoint(), payload, headers)

        text_parts, calls = [], []
        cand = (resp.get("candidates") or [{}])[0]
        for part in cand.get("content", {}).get("parts", []):
            if "text" in part:
                text_parts.append(part["text"])
            elif "functionCall" in part:
                fc = part["functionCall"]
                calls.append(ToolCall(id=f"call_{uuid.uuid4().hex[:8]}",
                                      name=fc["name"], arguments=fc.get("args", {})))

        return Completion(text="".join(text_parts), tool_calls=calls,
                          raw=resp, finish_reason=cand.get("finishReason", ""))
