"""A lightweight execution plan the model can author and track.

In plan mode the model is expected to call `create_plan` first — laying out the
steps it intends to take — and hold off on mutating actions until the user
approves. As it works, it marks steps active/done so you can watch progress.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Step:
    text: str
    status: str = "pending"      # pending | active | done


CURRENT: list[Step] = []


def set_plan(steps: list[str]) -> None:
    CURRENT[:] = [Step(s) for s in steps if s.strip()]


def update(index: int, status: str) -> bool:
    if 1 <= index <= len(CURRENT):
        CURRENT[index - 1].status = status
        return True
    return False


def clear() -> None:
    CURRENT.clear()


def as_text() -> str:
    if not CURRENT:
        return "(no plan)"
    mark = {"pending": "[ ]", "active": "[»]", "done": "[✓]"}
    return "\n".join(f"  {mark.get(s.status, '[ ]')} {i}. {s.text}"
                     for i, s in enumerate(CURRENT, 1))
