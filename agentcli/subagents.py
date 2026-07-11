"""Registry of sub-agents the model has spawned, so they can be shown in a
panel, opened to inspect their transcript, and have their behavior tweaked.

Sub-agents run synchronously (spawn_agent blocks until the child finishes), but
we keep them here afterward so you can review what a delegated task actually
did, and adjust the persona used for future spawns.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field


@dataclass
class SubAgent:
    id: str
    task: str
    persona: str
    status: str = "running"       # running | done | failed
    result: str = ""
    agent: object = None          # the child Agent (for its history)
    created: float = field(default_factory=time.time)


REGISTRY: list[SubAgent] = []
# a persona applied to EVERY spawned sub-agent unless it brings its own
DEFAULT_PERSONA = ""


def create(task: str, persona: str, agent) -> SubAgent:
    sa = SubAgent(id=uuid.uuid4().hex[:6], task=task,
                  persona=persona or DEFAULT_PERSONA, agent=agent)
    REGISTRY.append(sa)
    return sa


def active() -> list[SubAgent]:
    return [s for s in REGISTRY if s.status == "running"]


def recent(n: int = 6) -> list[SubAgent]:
    return REGISTRY[-n:]


def clear_done() -> int:
    global REGISTRY
    before = len(REGISTRY)
    REGISTRY = [s for s in REGISTRY if s.status == "running"]
    return before - len(REGISTRY)
