"""Conversation persistence — one file per conversation.

Each conversation is a JSONL file under ~/.agentcli/threads/<id>.jsonl:
the first line is a `_meta` record (provider, model, title, created), and
every following line is one message. This makes conversations portable,
greppable, individually deletable, and diff-friendly — no shared DB lock.

The public API matches the old sqlite store so nothing else changes.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

from .types import Message, ToolCall

DEFAULT_DIR = Path(os.environ.get(
    "AGENTCLI_THREADS", Path.home() / ".agentcli" / "threads"))


class Store:
    def __init__(self, root: Path = DEFAULT_DIR):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, conv_id: str) -> Path:
        return self.root / f"{conv_id}.jsonl"

    # --- conversations --------------------------------------------------
    def new_conversation(self, provider: str, model: str, title: str = "") -> str:
        cid = uuid.uuid4().hex[:12]
        meta = {"_meta": True, "id": cid, "provider": provider, "model": model,
                "created_at": time.time(), "title": title or "(untitled)"}
        with open(self._path(cid), "w", encoding="utf-8") as f:
            f.write(json.dumps(meta) + "\n")
        return cid

    def list_conversations(self, limit: int = 100) -> list[tuple]:
        rows = []
        for fp in self.root.glob("*.jsonl"):
            meta, n = self._read_meta(fp)
            if meta:
                rows.append((meta["id"], meta.get("provider", "?"),
                             meta.get("model", "?"), meta.get("created_at", 0),
                             meta.get("title", ""), n))
        rows.sort(key=lambda r: r[3], reverse=True)
        return rows[:limit]

    def _read_meta(self, fp: Path) -> tuple[dict | None, int]:
        try:
            with open(fp, "r", encoding="utf-8") as f:
                first = f.readline()
                meta = json.loads(first) if first else None
                if not meta or not meta.get("_meta"):
                    return None, 0
                n = sum(1 for _ in f)     # remaining lines = message count
                return meta, n
        except (OSError, json.JSONDecodeError):
            return None, 0

    def delete(self, conv_id: str) -> bool:
        p = self._path(conv_id)
        if p.exists():
            p.unlink()
            return True
        return False

    # --- messages -------------------------------------------------------
    def append(self, conv_id: str, seq: int, msg: Message) -> None:
        record = {
            "role": msg.role, "content": msg.content,
            "tool_calls": [{"id": t.id, "name": t.name, "arguments": t.arguments}
                           for t in msg.tool_calls],
            "tool_call_id": msg.tool_call_id, "name": msg.name,
        }
        p = self._path(conv_id)
        if not p.exists():                # conversation file missing? recreate meta
            self.new_conversation("?", "?")
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def _iter_messages(self, conv_id: str):
        p = self._path(conv_id)
        if not p.exists():
            return
        with open(p, "r", encoding="utf-8") as f:
            f.readline()                  # skip meta
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)

    def load_messages(self, conv_id: str) -> list[Message]:
        out: list[Message] = []
        for r in self._iter_messages(conv_id):
            calls = [ToolCall(t["id"], t["name"], t["arguments"])
                     for t in r.get("tool_calls", [])]
            out.append(Message(role=r["role"], content=r.get("content", ""),
                               tool_calls=calls, tool_call_id=r.get("tool_call_id"),
                               name=r.get("name")))
        return out

    def preview(self, conv_id: str, limit: int = 6) -> str:
        lines = []
        for r in self._iter_messages(conv_id):
            if r["role"] in ("user", "assistant") and r.get("content"):
                lines.append(f"{r['role']}: {r['content'][:100]}")
                if len(lines) >= limit:
                    break
        return "\n".join(lines)
