"""Context compaction — summarize older turns so a long conversation keeps
fitting in the model's window.

The system message and the most recent turns are kept verbatim; everything
before that is replaced by a single model-written summary folded into the
system prompt. Runs manually (/compact) or automatically past a token budget.
"""
from __future__ import annotations

from .types import Message

# rough chars-per-token; good enough for a budget trigger
_CHARS_PER_TOKEN = 4


def estimate_tokens(history: list[Message]) -> int:
    total = 0
    for m in history:
        total += len(m.content or "")
        for tc in m.tool_calls:
            total += len(str(tc.arguments))
    return total // _CHARS_PER_TOKEN


def _transcript(msgs: list[Message]) -> str:
    lines = []
    for m in msgs:
        if m.role == "tool":
            lines.append(f"[tool:{m.name}] {m.content[:400]}")
        elif m.tool_calls:
            calls = ", ".join(f"{tc.name}({tc.arguments})" for tc in m.tool_calls)
            lines.append(f"assistant: {m.content} «calls: {calls}»")
        else:
            lines.append(f"{m.role}: {m.content}")
    return "\n".join(lines)


def compact(agent, keep_recent: int = 4) -> dict | None:
    """Summarize everything but the last `keep_recent` turns. Returns stats,
    or None if there wasn't enough to compact."""
    history = agent.history
    system = next((m for m in history if m.role == "system"), None)
    convo = [m for m in history if m.role != "system"]
    if len(convo) <= keep_recent + 2:
        return None

    older = convo[:-keep_recent]
    recent = convo[-keep_recent:]
    # never let `recent` begin on a tool result whose call got summarized away
    while recent and recent[0].role == "tool":
        older.append(recent.pop(0))
    if not older:
        return None

    before_tokens = estimate_tokens(history)

    summary = agent.provider.chat(
        [Message("system",
                 "You compress conversations. Summarize the exchange below in "
                 "tight bullet points. Preserve decisions made, concrete facts, "
                 "file paths, code identifiers, and any unfinished tasks. Omit "
                 "pleasantries. This summary replaces the raw history."),
         Message("user", _transcript(older))],
        tools=[], temperature=0.2, max_tokens=1024).text.strip()

    base = system.content if system else ""
    new_system = base + "\n\n## Summary of earlier conversation\n" + summary
    agent.history = [Message("system", new_system)] + recent
    # NOTE: do not reset agent._seq — it's the sqlite high-water mark; resetting
    # it would make future appends collide with already-persisted rows.

    after_tokens = estimate_tokens(agent.history)
    return {"summarized": len(older), "kept": len(recent),
            "before": before_tokens, "after": after_tokens}
