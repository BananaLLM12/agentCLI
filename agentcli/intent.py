"""Intent flagger — inspects what the MODEL is about to *do* before it happens.

The injection guard watches untrusted INPUT. This watches the model's OUTPUT:
the shell commands it wants to run and the code/content it wants to write. If a
tool call looks destructive or malicious (fork bomb, rm -rf /, reverse shell,
credential exfiltration, keylogger…), it's escalated — forced through approval
even in auto mode, or blocked outright when catastrophic.

Weighted so ordinary work (`rm -rf build`, `chmod +x run.sh`) passes, while the
genuinely dangerous shapes get caught.
"""
from __future__ import annotations

import re

# (pattern, weight, label). weight >=5 = block; >=3 = force approval.
_RULES: list[tuple[re.Pattern, int, str]] = [
    (re.compile(r"\brm\s+-[rf]{1,2}\s+(/|~|\$HOME|/\*|\*|\.)(\s|$)"), 5, "wipe-root"),
    (re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:"), 5, "fork-bomb"),
    (re.compile(r"\bdd\b[^\n]*\bof=/dev/(sd|nvme|disk|hd|mmc)"), 5, "disk-wipe"),
    (re.compile(r">\s*/dev/(sd|nvme|disk|hd)"), 5, "disk-write"),
    (re.compile(r"\bmkfs(\.\w+)?\s+/dev/"), 5, "format-disk"),
    (re.compile(r"\bbash\s+-i\b[^\n]*/dev/tcp/|/dev/tcp/\d{1,3}(\.\d{1,3}){3}"), 5, "reverse-shell"),
    (re.compile(r"os\.system\([^)]*rm\s+-rf\s+/|shutil\.rmtree\(\s*['\"]?(/|~)"), 5, "wipe-root"),
    (re.compile(r"\b(curl|wget)\b[^|\n]*\|\s*(sudo\s+)?(ba|z|d)?sh\b"), 4, "remote-exec"),
    (re.compile(r"(cat|cp|scp|curl|nc|tar)\b[^\n]*"
                r"(/etc/shadow|/etc/passwd|\.ssh/id_[rd]sa|\.aws/credentials|"
                r"\.env\b|\.git-credentials)"), 4, "cred-exfil"),
    (re.compile(r"\b(pynput|GetAsyncKeyState)\b|SetWindowsHookEx[^\n]*WH_KEYBOARD"
                r"|keylog", re.I), 4, "keylogger"),
    (re.compile(r"\b(iptables\s+-F|ufw\s+disable)\b|systemctl\s+(stop|disable)\s+"
                r"[^\n]*(firewall|defender|apparmor)", re.I), 3, "disable-security"),
    (re.compile(r"chmod\s+-R?\s*777\s+/(\s|$)"), 3, "perm-root"),
    (re.compile(r"\bhistory\s+-c\b|>\s*~?/?\.bash_history"), 2, "anti-forensics"),
    (re.compile(r"\bsudo\s+rm\s+-rf\b"), 4, "destructive-sudo"),
]

BLOCK_SCORE = 5      # catastrophic -> refuse
APPROVE_SCORE = 3    # dangerous -> force human approval even in auto

# which argument fields carry the model's "intent" per tool
_FIELDS = {
    "run_shell": ("command",),
    "run_background": ("command",),
    "write_file": ("path", "content"),
    "append_file": ("path", "content"),
    "edit_file": ("path", "new"),
    "replace_lines": ("path", "content"),
    "insert_lines": ("path", "content"),
    "delete_path": ("path",),
    "http_post": ("url",),
    "move_path": ("dst",),
}


def scan(text: str) -> list[tuple[int, str]]:
    return [(w, label) for rx, w, label in _RULES if rx.search(text or "")]


import os

# deleting/moving any of these is catastrophic
_CRITICAL_PATHS = {"/", "/etc", "/usr", "/bin", "/sbin", "/var", "/lib",
                   "/boot", "/dev", "/System", "/Library", "/Applications"}


def _is_critical_path(raw: str) -> bool:
    raw = str(raw).strip()
    if raw in ("~", "$HOME", "/*", "*", "~/", "/"):
        return True
    norm = os.path.normpath(os.path.expanduser(raw))
    return norm == os.path.expanduser("~") or norm in _CRITICAL_PATHS


def check(tool: str, args: dict) -> tuple[int, list[str]]:
    """Return (max_severity_score, [labels]) for a tool call's intent."""
    # direct filesystem tools: a bare critical path is catastrophic
    if tool in ("delete_path", "move_path"):
        for key in ("path", "src"):
            if key in args and _is_critical_path(args[key]):
                return 5, ["delete-critical"]

    fields = _FIELDS.get(tool)
    if not fields:
        return 0, []
    blob = "\n".join(str(args.get(f, "")) for f in fields)
    hits = scan(blob)
    if not hits:
        return 0, []
    return max(w for w, _ in hits), sorted({l for _, l in hits})
