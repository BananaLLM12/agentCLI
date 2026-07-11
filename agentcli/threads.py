"""Side threads — multiple independent conversations in one session.

Each thread is its own Agent (own history + persona + sqlite conversation), so
you can spin up a side chat to ask something without disturbing the main one,
then switch back. The main thread is always thread 0.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Thread:
    name: str
    agent: object          # an Agent
    persona: str = ""


class ThreadManager:
    def __init__(self, main_agent, main_name: str = "main"):
        self.threads: list[Thread] = [Thread(main_name, main_agent)]
        self.active_index = 0

    @property
    def active(self) -> Thread:
        return self.threads[self.active_index]

    def add(self, name: str, agent, persona: str = "") -> int:
        self.threads.append(Thread(name, agent, persona))
        self.active_index = len(self.threads) - 1
        return self.active_index

    def switch(self, ident: str) -> bool:
        """Switch by index or name. Returns True on success."""
        if ident.isdigit():
            i = int(ident)
            if 0 <= i < len(self.threads):
                self.active_index = i
                return True
            return False
        for i, t in enumerate(self.threads):
            if t.name == ident:
                self.active_index = i
                return True
        return False

    def listing(self) -> list[tuple[int, str, int, bool]]:
        """(index, name, message_count, is_active) for each thread."""
        return [(i, t.name, len(t.agent.history), i == self.active_index)
                for i, t in enumerate(self.threads)]
