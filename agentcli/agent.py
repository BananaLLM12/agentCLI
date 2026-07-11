"""The agent loop. Provider-agnostic: it only speaks in Message/Completion.

Flow per turn:
  1. send the running transcript + tool specs to the provider
  2. if the model returned tool calls -> run each, append results, loop
  3. otherwise -> return the assistant's text
A hard cap on iterations stops runaway tool loops. Optionally streams tokens
and persists every message to a Store.
"""
from __future__ import annotations

import re
from typing import Callable, Optional

from . import tools
from .providers.base import Provider
from .store import Store
from .types import Message


def _extract_limit(msg: str) -> int | None:
    """Pull a token limit out of a rate/size error, e.g.
    '... (TPM): Limit 8000, Requested 33000' -> 8000."""
    m = re.search(r"limit[^0-9]{0,8}(\d[\d,]{2,})", msg, re.IGNORECASE)
    if m:
        try:
            return int(m.group(1).replace(",", ""))
        except ValueError:
            return None
    return None


class Agent:
    def __init__(self, provider: Provider, system: str = "",
                 max_steps: int = 8, temperature: float = 0.7,
                 max_tokens: int = 1024, use_tools: bool = True,
                 stream: bool = False,
                 store: Optional[Store] = None, conv_id: Optional[str] = None,
                 policy=None, approver: Optional[Callable] = None,
                 auto_compact: bool = True, compact_at: int = 12000,
                 on_event: Optional[Callable[[str, str], None]] = None):
        from .permissions import Policy
        self.provider = provider
        self.max_steps = max_steps
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.use_tools = use_tools
        self.stream = stream
        self.auto_compact = auto_compact
        self.compact_at = compact_at
        self.plan_mode = False
        self.education = None      # subject string when in education mode
        self.store = store
        self.conv_id = conv_id
        self.policy = policy or Policy()
        # approver(tool, args, reason) -> 'yes' | 'no' | 'always' | 'quit'
        self.approver = approver
        self.on_event = on_event or (lambda kind, text: None)
        self.history: list[Message] = []
        self.last_turn: dict = {"tool_calls": 0, "seconds": 0.0}
        self._seq = 0
        if system:
            self._add(Message(role="system", content=system))

    def _add(self, msg: Message) -> None:
        """Append to in-memory history and, if configured, persist it."""
        self.history.append(msg)
        if self.store and self.conv_id:
            self.store.append(self.conv_id, self._seq, msg)
        self._seq += 1

    def load_history(self, messages: list[Message]) -> None:
        """Seed history from a resumed conversation (does not re-persist)."""
        self.history = list(messages)
        self._seq = len(messages)

    _MAX_BUDGET = 16384   # ceiling when growing after truncation
    _MIN_BUDGET = 256     # floor when shrinking to fit a rate/size limit

    def _call(self, specs):
        """One provider round trip, self-tuning the token budget both ways.

        • Truncated output (finish_reason=length, or a provider 400 on a
          cut-off tool call) -> GROW the budget and retry.
        • "Request too large" / TPM 413 -> the reserved max_tokens exceeds the
          tier's per-minute allowance -> SHRINK the budget and retry, honoring
          any explicit "Limit N" in the error.
        """
        from .http import HTTPError

        budget = max(self.max_tokens, self._MIN_BUDGET)
        active_specs = specs
        func_fails = 0
        # append transient directives (mode-specific, not persisted to history)
        directives = []
        if self.plan_mode:
            directives.append(
                "PLAN MODE is ON. Do NOT execute any mutating action (writing "
                "files, running shell, deleting, etc.). First call create_plan "
                "with a concise ordered list of the steps you intend to take, "
                "present it in prose, and STOP. The user will approve first.")
        if self.education:
            directives.append(
                f"EDUCATION MODE — you are tutoring the user on: {self.education}. "
                "Teach interactively and in small bites: explain one concept "
                "clearly, show a short illustrative snippet, then pose ONE "
                "question or tiny exercise and STOP to let them answer. When they "
                "reply, grade it warmly, correct mistakes with a hint, and move "
                "to the next bite. Periodically quiz them on earlier material. "
                "Adapt the difficulty to how they're doing. Keep it engaging.")
        base_history = self.history
        if directives:
            base_history = self.history + [Message(role="system",
                                                   content="\n\n".join(directives))]
        while True:
            # spinner only wraps the model round-trip (not tool runs / prompts)
            spin = not self.stream
            if spin:
                self.on_event("thinking", "start")
            try:
                if self.stream:
                    c = self.provider.stream(
                        base_history, active_specs,
                        on_delta=lambda d: self.on_event("delta", d),
                        temperature=self.temperature, max_tokens=budget)
                else:
                    c = self.provider.chat(
                        base_history, active_specs,
                        temperature=self.temperature, max_tokens=budget)
            except HTTPError as e:
                if spin:
                    self.on_event("thinking", "stop")
                msg = str(e).lower()
                # -- too large for the tier: shrink and retry --
                too_big = e.status == 413 or "too large" in msg or "tokens per minute" in msg
                if too_big and budget > self._MIN_BUDGET:
                    limit = _extract_limit(str(e))
                    if limit:
                        budget = max(self._MIN_BUDGET, min(budget // 2, limit - 512))
                    else:
                        budget = max(self._MIN_BUDGET, budget // 2)
                    self.on_event("retry", f"request too large for your tier — "
                                           f"shrinking to max_tokens={budget}")
                    continue
                # -- model botched the function-call format (common on small
                #    models w/ many tools): retry, then fall back to no tools.
                #    Checked BEFORE truncation so it isn't mistaken for one. --
                func_fail = e.status == 400 and (
                    "failed to call a function" in msg
                    or "failed_generation" in msg
                    or "botched a tool call" in msg)
                if func_fail and active_specs and func_fails < 2:
                    func_fails += 1
                    if func_fails == 2:
                        active_specs = []      # last try: let it just answer
                        self.on_event("retry", "model kept fumbling tool calls — "
                                               "answering without tools")
                    else:
                        self.on_event("retry", "malformed tool call — retrying")
                    continue
                # -- truncated tool-call ARGUMENTS: grow and retry --
                if (e.status == 400 and budget < self._MAX_BUDGET
                        and ("tool call argument" in msg or "parse tool call" in msg)):
                    budget = min(budget * 2, self._MAX_BUDGET)
                    self.on_event("retry", f"tool call truncated — retrying with "
                                           f"max_tokens={budget}")
                    continue
                raise

            if spin:
                self.on_event("thinking", "stop")

            # ran out of room mid-generation -> grow and retry
            if c.finish_reason in ("length", "max_tokens") and budget < self._MAX_BUDGET:
                budget = min(budget * 2, self._MAX_BUDGET)
                self.on_event("retry", f"response hit the token limit — retrying "
                                       f"with max_tokens={budget}")
                continue
            return c

    def send(self, user_text: str, images=None) -> str:
        """Run one user turn to completion (through any tool calls)."""
        import time as _t

        from . import notify as _notify
        from . import tools as _tools
        _notify.reset_turn()                     # fresh "did we notify?" flag
        _tools.set_active_agent(self)            # so spawn_agent can reach us
        started = _t.monotonic()
        tool_calls = 0

        # auto-compact if the running context has grown too large
        if self.auto_compact:
            from . import compact as _compact
            if _compact.estimate_tokens(self.history) > self.compact_at:
                self.compact()

        from . import guard as _guard
        # low-power: after severe/repeated abuse the tool stops engaging
        if _guard.GUARD.low_power:
            self.last_turn = {"tool_calls": 0, "seconds": 0.0}
            return "no."

        # scan the incoming line — a flagged jailbreak NEVER reaches the model
        r = self._guard_assess(user_text, "user")
        if r.get("low_power"):
            self.last_turn = {"tool_calls": 0, "seconds": 0.0}
            return "no."
        if r["attempt"]:
            self.last_turn = {"tool_calls": 0, "seconds": 0.0}
            return ("⚠ Blocked: that reads as a prompt-injection / jailbreak "
                    "attempt, so I won't process it. (Restart the CLI if this "
                    "was a false positive.)")

        self._add(Message(role="user", content=user_text, images=images or []))
        specs = tools.specs() if self.use_tools else []

        try:
            for _ in range(self.max_steps):
                completion = self._call(specs)

                self._add(Message(role="assistant", content=completion.text,
                                  tool_calls=completion.tool_calls))

                if not completion.tool_calls:
                    # the caller renders the final reply (bot label + markdown);
                    # emitting it here too would double-print it
                    return completion.text

                # narrate what it's about to do BEFORE running the tools
                # (in streaming the text already flowed via deltas)
                if completion.text.strip() and not self.stream:
                    self.on_event("preamble", completion.text)

                for call in completion.tool_calls:
                    tool_calls += 1
                    self.on_event("tool_call", (call.name, call.arguments))
                    result = self._run_tool(call.name, call.arguments)
                    # tool output is untrusted — scan before it re-enters context
                    poisoned = self._guard_assess(result, f"tool:{call.name}")["attempt"]
                    if poisoned:
                        # withhold the injected content and stop this turn so it
                        # can't steer the model
                        self._add(Message(role="tool",
                                          content="[withheld: content contained "
                                          "an injection attempt]",
                                          tool_call_id=call.id, name=call.name))
                        return ("⚠ Blocked: the content from "
                                f"{call.name} contained an injection attempt. I "
                                "stopped and did not act on it.")
                    self.on_event("tool_result", result)
                    self._add(Message(role="tool", content=result,
                                      tool_call_id=call.id, name=call.name))
        except KeyboardInterrupt:
            # Ctrl-C mid-run: leave the transcript valid and bail this turn
            self._heal_history()
            self.on_event("interrupted", "")
            return "(interrupted)"
        finally:
            self.last_turn = {"tool_calls": tool_calls,
                              "seconds": _t.monotonic() - started}

        return "(stopped: hit max tool-call steps)"

    def _heal_history(self) -> None:
        """After an interrupt, make sure every assistant tool_call has a tool
        result — an unanswered call would make the provider reject the next
        turn. Fills any gaps with a placeholder result."""
        if not self.history:
            return
        # find the last assistant message that issued tool calls
        last_asst = None
        for m in reversed(self.history):
            if m.role == "assistant" and m.tool_calls:
                last_asst = m
                break
        if not last_asst:
            return
        answered = {m.tool_call_id for m in self.history if m.role == "tool"}
        for call in last_asst.tool_calls:
            if call.id not in answered:
                self._add(Message(role="tool", content="[interrupted by user]",
                                  tool_call_id=call.id, name=call.name))

    def compact(self, keep_recent: int = 4) -> dict | None:
        """Summarize older turns into the system prompt. Returns stats or None."""
        from . import compact as _compact
        stats = _compact.compact(self, keep_recent=keep_recent)
        if stats:
            self.on_event("compact",
                          f"summarized {stats['summarized']} msgs · "
                          f"~{stats['before']}→{stats['after']} tokens")
        return stats

    def spawn(self, task: str, persona: str = "", model: str | None = None) -> str:
        """Create a fresh child agent (same provider/policy) to handle a
        subtask in isolation, and return just its final answer. The child has
        its own history, so it never pollutes this conversation."""
        import copy

        prov = self.provider
        if model:                       # optional different model for the child
            prov = copy.copy(prov)
            prov.model = model

        sys_prompt = ((persona.strip() + "\n\n") if persona else "") + (
            "You are a focused sub-agent. Complete the assigned task using your "
            "tools, then report the result concisely. Do not ask questions.")

        from . import subagents
        # apply a session-wide default sub-agent persona if none was given
        if not persona and subagents.DEFAULT_PERSONA:
            persona = subagents.DEFAULT_PERSONA
            sys_prompt = persona.strip() + "\n\n" + sys_prompt

        child = Agent(prov, system=sys_prompt, max_steps=self.max_steps,
                      temperature=self.temperature, max_tokens=self.max_tokens,
                      use_tools=self.use_tools, stream=False,
                      policy=self.policy, approver=self.approver,
                      on_event=lambda k, t: self.on_event(
                          "sub", t[0] if k == "tool_call" and isinstance(t, tuple)
                          else str(t)) if k in ("tool_call", "denied") else None)
        sa = subagents.create(task, persona, child)
        try:
            result = child.send(task)
            sa.status, sa.result = "done", result
            return result
        except Exception as e:
            sa.status, sa.result = "failed", repr(e)
            raise
        finally:
            # child.send() re-pointed the active agent at itself; restore us so
            # any further tool calls in this turn spawn from the right place
            from . import tools as _tools
            _tools.set_active_agent(self)

    def _guard_assess(self, text: str, source: str) -> dict:
        """Run text through the injection guard and react to escalations.
        Returns the assessment (caller short-circuits the turn on an attempt)."""
        from . import guard
        from .permissions import Mode
        r = guard.GUARD.assess(text, source)
        if not r["attempt"]:
            return r
        labels = ", ".join(r["labels"])
        if r["locked"]:
            # freeze everything
            self.policy.mode = Mode.READONLY
            self.policy.allow_shell = False
            self.policy.allow_network = False
            self.on_event("locked",
                          f"injection attempt from {source} [{labels}] — "
                          f"SESSION LOCKED")
        elif r["hardened"] or guard.GUARD.level >= 1:
            # tighten the blast radius but keep going
            self.policy.mode = Mode.READONLY
            self.policy.allow_shell = False
            self.policy.allow_network = False
            self.on_event("security",
                          f"injection attempt from {source} [{labels}] — "
                          f"hardened to read-only")
        return r

    def _run_tool(self, name: str, args: dict) -> str:
        """Consult the injection guard, then the permission policy, then run."""
        from . import guard
        from .permissions import Decision

        if guard.GUARD.locked:
            return "[session locked by security guard — tool use disabled]"

        # plan mode: allow only planning + read-only inspection, block mutations
        if self.plan_mode:
            from .permissions import MUTATING
            if name in MUTATING:
                return ("[plan mode: present the plan and wait for approval "
                        "before running mutating actions]")

        # intent flagger: inspect what the MODEL is about to DO (its commands /
        # generated code), independent of the permission mode
        from . import intent
        sev, labels = intent.check(name, args)
        if sev >= intent.BLOCK_SCORE:
            self.on_event("intent", f"BLOCKED {name} [{', '.join(labels)}] — "
                                    f"looks catastrophic")
            # a dangerous self-directed action also hardens the session
            from .permissions import Mode
            self.policy.mode = Mode.READONLY
            return f"[blocked by intent guard: {', '.join(labels)}]"

        decision, reason = self.policy.evaluate(name, args)

        # dangerous-but-not-catastrophic: force approval even in auto mode
        if sev >= intent.APPROVE_SCORE and decision == Decision.ALLOW:
            self.on_event("intent", f"{name} flagged [{', '.join(labels)}] — "
                                    f"requiring approval")
            decision = Decision.ASK
            reason = f"intent flagged: {', '.join(labels)}"

        if decision == Decision.DENY:
            self.on_event("denied", f"{name}: {reason}")
            return f"[permission denied: {reason}]"

        if decision == Decision.ASK:
            if not self.approver:   # non-interactive: refuse rather than guess
                self.on_event("denied", f"{name}: needs approval "
                                        f"(run interactively or use --mode auto)")
                return "[permission denied: this action needs approval]"
            ans = self.approver(name, args, reason)
            if ans == "always":
                self.policy.session_allow.add(name)
            elif ans == "quit":
                return "[stopped by user]"
            elif ans != "yes":
                self.on_event("denied", f"{name}: skipped by user")
                return "[skipped by user]"

        return tools.run(name, args)
