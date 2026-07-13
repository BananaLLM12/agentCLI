"""Tiny JSON-over-HTTP helper built on the stdlib, so the tool has no
hard dependencies. Adds a browser-ish User-Agent (some gateways / Cloudflare
reject the default `Python-urllib` UA with a 403) and automatic retry with
exponential backoff on transient failures.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Iterator

# Cloudflare-fronted APIs (openrouter, groq, deepseek, …) 403 the stock
# urllib User-Agent. A normal-looking UA sails through.
DEFAULT_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) agentcli/1.0")

# transient HTTP statuses worth retrying
RETRY_STATUS = {408, 425, 429, 500, 502, 503, 504}
MAX_RETRIES = 3


class HTTPError(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(short_error(status, body))
        self.status = status
        self.body = body


def short_error(status: int, body: str) -> str:
    """Turn a raw error body into one readable line."""
    detail = ""
    try:  # most providers wrap the reason in {"error": {"message": ...}}
        j = json.loads(body)
        err = j.get("error", j)
        detail = err.get("message") if isinstance(err, dict) else str(err)
    except (json.JSONDecodeError, AttributeError):
        detail = body.strip().replace("\n", " ")[:160]

    hint = {
        401: "bad or missing API key",
        403: "blocked (403) — often a firewall/UA or region/credit issue",
        404: "model or endpoint not found — check the model id",
        413: "request too large for your tier — lower --max-tokens",
        429: "rate limited — slow down or check your quota",
    }.get(status, "")
    if "1010" in (detail or ""):
        hint = "Cloudflare blocked the request (UA/firewall)"
    if status == 400 and "tool call" in (detail or "").lower():
        hint = "tool call was truncated — raise --max-tokens"
    if status == 400 and ("failed to call a function" in (detail or "").lower()
                          or "failed_generation" in (detail or "").lower()):
        hint = "model botched a tool call — try a stronger model"
    _d = (detail or "").lower()
    if ("image" in _d or "vision" in _d or "multimodal" in _d) and \
            ("support" in _d or "invalid" in _d or "not " in _d):
        hint = ("this model can't see images — switch to a vision model "
                "(gpt-4o, claude-3.5+, gemini)")
    parts = [f"HTTP {status}"]
    if hint:
        parts.append(hint)
    if detail and detail not in hint:
        parts.append(f"— {detail[:160]}")
    return " ".join(parts)


def _headers(headers: dict[str, str]) -> dict[str, str]:
    merged = {"User-Agent": DEFAULT_UA, "Content-Type": "application/json"}
    merged.update(headers)
    return merged


def _backoff(attempt: int, exc: Exception) -> None:
    # 0.5s, 1s, 2s … honoring Retry-After when the server sends one
    wait = 0.5 * (2 ** attempt)
    hdrs = getattr(exc, "headers", None)
    retry_after = hdrs.get("Retry-After") if hdrs else None
    if retry_after and str(retry_after).isdigit():
        wait = float(retry_after)
    time.sleep(wait)


def _request(url: str, payload: dict[str, Any], headers: dict[str, str],
             timeout: float, stream: bool):
    """Open a POST with retries. Returns the live response object."""
    body = json.dumps(payload).encode("utf-8")
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        req = urllib.request.Request(url, data=body, method="POST")
        for k, v in _headers(headers).items():
            req.add_header(k, v)
        if stream:
            req.add_header("Accept", "text/event-stream")
        try:
            return urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as e:
            if e.code in RETRY_STATUS and attempt < MAX_RETRIES:
                _backoff(attempt, e)
                last_exc = e
                continue
            raise HTTPError(e.code, e.read().decode("utf-8", "replace")) from None
        except urllib.error.URLError as e:  # DNS, connection reset, timeout
            if attempt < MAX_RETRIES:
                _backoff(attempt, e)
                last_exc = e
                continue
            raise HTTPError(0, f"network error: {e.reason}") from None
    raise HTTPError(0, f"failed after {MAX_RETRIES} retries: {last_exc}")


def post_json(url: str, payload: dict[str, Any], headers: dict[str, str],
              timeout: float = 120.0) -> dict[str, Any]:
    with _request(url, payload, headers, timeout, stream=False) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_json(url: str, headers: dict[str, str],
             timeout: float = 30.0) -> dict[str, Any]:
    """GET returning JSON, with the same UA + retry treatment."""
    req = urllib.request.Request(url, method="GET")
    for k, v in _headers(headers).items():
        req.add_header(k, v)
    for attempt in range(MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in RETRY_STATUS and attempt < MAX_RETRIES:
                _backoff(attempt, e); continue
            raise HTTPError(e.code, e.read().decode("utf-8", "replace")) from None
        except urllib.error.URLError as e:
            if attempt < MAX_RETRIES:
                _backoff(attempt, e); continue
            raise HTTPError(0, f"network error: {e.reason}") from None
    raise HTTPError(0, "unreachable")


def stream_sse(url: str, payload: dict[str, Any], headers: dict[str, str],
               timeout: float = 120.0) -> Iterator[dict[str, Any]]:
    """POST and yield parsed `data:` JSON objects from an SSE stream."""
    with _request(url, {**payload, "stream": True}, headers, timeout, stream=True) as resp:
        yield from parse_sse_lines(
            (raw.decode("utf-8", "replace") for raw in resp))


def parse_sse_lines(lines: Iterator[str]) -> Iterator[dict[str, Any]]:
    """Pure SSE-line -> JSON parser, unit-testable without a live socket."""
    for raw in lines:
        line = raw.strip()
        if not line or not line.startswith("data:"):
            continue
        chunk = line[5:].strip()
        if chunk == "[DONE]":
            break
        try:
            yield json.loads(chunk)
        except json.JSONDecodeError:
            continue
