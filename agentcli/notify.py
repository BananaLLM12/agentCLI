"""User notification — a completion banner in the terminal, a bell, and a
desktop notification when the user has tabbed away.

Used two ways:
  • the model calls the `notify` tool when it finishes / is blocked on real work
  • the CLI auto-fires one after a "heavy" turn (long, or many tool calls),
    or whenever the terminal isn't the focused window
"""
from __future__ import annotations

import platform
import subprocess
import sys
import time

from . import ui

# set true whenever a notification fires during the current turn, so the CLI's
# auto-notifier doesn't double up on a turn the model already announced.
NOTIFIED_THIS_TURN = False

_TERMINALS = {"Terminal", "iTerm2", "iTerm", "Warp", "WarpPreview", "Alacritty",
              "kitty", "WezTerm", "Ghostty", "Code", "Hyper", "Tabby", "rio"}


def reset_turn() -> None:
    global NOTIFIED_THIS_TURN
    NOTIFIED_THIS_TURN = False


def _frontmost_app() -> str | None:
    """Name of the frontmost macOS app, or None if we can't tell."""
    if platform.system() != "Darwin":
        return None
    try:
        out = subprocess.run(
            ["osascript", "-e",
             'tell application "System Events" to get name of first '
             'application process whose frontmost is true'],
            capture_output=True, text=True, timeout=2)
        return out.stdout.strip() or None
    except Exception:
        return None


def terminal_focused() -> bool:
    """Best-effort: is the user looking at the terminal right now?

    macOS: compare the frontmost app to a known-terminal set. Elsewhere we
    can't cheaply tell, so assume focused (auto-notify then leans on the
    'heavy work' heuristic instead of focus).
    """
    app = _frontmost_app()
    if app is None:
        return True
    return app in _TERMINALS


def _desktop_notification(title: str, message: str) -> None:
    """Fire an OS-level notification (best effort, silent on failure)."""
    system = platform.system()
    try:
        if system == "Darwin":
            safe = message.replace('"', "'")[:200]
            st = title.replace('"', "'")[:80]
            subprocess.run(
                ["osascript", "-e",
                 f'display notification "{safe}" with title "{st}" sound name "Glass"'],
                capture_output=True, timeout=3)
        elif system == "Linux":
            subprocess.run(["notify-send", title, message],
                           capture_output=True, timeout=3)
    except Exception:
        pass


def notify(title: str, message: str, status: str = "done",
           force: bool = False, source: str = "auto") -> None:
    """Announce completion. Banner + bell always; desktop notification only
    when the terminal is unfocused (or force=True)."""
    global NOTIFIED_THIS_TURN
    NOTIFIED_THIS_TURN = True

    # in-terminal banner + bell
    print("\n" + ui.notify_banner(title, message, status), file=sys.stderr)
    if ui._ENABLED:
        sys.stderr.write("\a")   # terminal bell
        sys.stderr.flush()

    # desktop notification only if they've looked away (or forced)
    if force or not terminal_focused():
        _desktop_notification(title, message)
