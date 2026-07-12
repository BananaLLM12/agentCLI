"""Permission policy — how much the agent is allowed to do on its own.

Three modes, mirroring the codex/claude-code model:
  • read-only : may inspect (read_file, http_get) but NEVER mutates. Any
                shell or file write is denied. Good for "just look / plan".
  • approve   : read freely, but every mutating action asks you first
                (yes / no / always-this-session). The safe default.
  • auto      : run everything without asking — subject to the restrictions
                below (path allowlist, network off, shell off).

Restrictions apply in every mode, as a hard floor:
  • allow_paths   : file reads/writes must stay under these roots
  • allow_network : http_get toggle
  • allow_shell   : run_shell toggle
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum


class Mode(str, Enum):
    READONLY = "read-only"
    APPROVE = "approve"
    AUTO = "auto"


class Decision(Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


# tools that change the world (vs. purely observe it)
MUTATING = {"run_shell", "run_background", "write_file", "append_file",
            "edit_file", "replace_lines", "insert_lines", "make_dir",
            "move_path", "copy_path", "delete_path", "http_post"}
# tools whose target paths must stay within allow_paths (checks path/src/dst)
FILE_TOOLS = {"read_file", "write_file", "append_file", "edit_file",
              "replace_lines", "insert_lines", "read_lines", "inspect_image",
              "list_dir", "find_files", "search_text", "make_dir", "move_path",
              "copy_path", "delete_path"}
_PATH_KEYS = ("path", "src", "dst")


def _within(path: str, roots: list[str]) -> bool:
    ap = os.path.realpath(os.path.expanduser(path))
    for r in roots:
        rp = os.path.realpath(os.path.expanduser(r))
        if ap == rp or ap.startswith(rp + os.sep):
            return True
    return False


@dataclass
class Policy:
    mode: Mode = Mode.APPROVE
    allow_paths: list[str] | None = None       # None = anywhere
    allow_network: bool = True
    allow_shell: bool = True
    # tools the policy file forbids outright — refused in every mode
    declined_tools: set[str] = field(default_factory=set)
    # tools the user chose "always" for, this session only
    session_allow: set[str] = field(default_factory=set)

    def evaluate(self, tool: str, args: dict) -> tuple[Decision, str]:
        # --- policy-file hard blocks (highest precedence) ---
        if tool in self.declined_tools:
            return Decision.DENY, "disabled by operating policy"

        # --- hard restrictions (apply in ALL modes) ---
        if tool == "http_get" and not self.allow_network:
            return Decision.DENY, "network access is disabled"
        if tool == "run_shell" and not self.allow_shell:
            return Decision.DENY, "shell access is disabled"
        if tool in FILE_TOOLS and self.allow_paths:
            for key in _PATH_KEYS:
                p = args.get(key)
                if p and not _within(p, self.allow_paths):
                    return Decision.DENY, f"path '{p}' is outside the allowed folders"

        # --- read-only mode blocks all mutation ---
        if self.mode == Mode.READONLY and tool in MUTATING:
            return Decision.DENY, "read-only mode — mutations are blocked"

        # --- session 'always' grants ---
        if tool in self.session_allow:
            return Decision.ALLOW, ""

        # --- auto runs everything the restrictions permitted ---
        if self.mode == Mode.AUTO:
            return Decision.ALLOW, ""

        # --- approve mode: mutating asks, reads pass ---
        if tool in MUTATING:
            return Decision.ASK, ""
        return Decision.ALLOW, ""

    def describe(self) -> str:
        bits = [self.mode.value]
        if self.allow_paths:
            bits.append("paths=" + ",".join(self.allow_paths))
        if not self.allow_network:
            bits.append("no-network")
        if not self.allow_shell:
            bits.append("no-shell")
        return " · ".join(bits)
