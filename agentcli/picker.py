"""An interactive, full-screen list picker for the terminal — arrow keys to
move, type to filter, Enter to choose, Esc to cancel. Pure stdlib (termios +
ANSI), so no curses dependency.

pick(items) -> the chosen item's original index, or None if cancelled.
Each item is a dict with a 'label' (one line) and optional 'preview' (lines).
"""
from __future__ import annotations

import os
import select
import sys

from . import ui

try:
    import termios
    import tty
    _HAS_TTY = True
except ImportError:                     # Windows / no termios
    _HAS_TTY = False


def _read_key(fd) -> str:
    """Read one logical keypress, decoding arrow-key escape sequences.

    Reads straight from the file descriptor with os.read (NOT sys.stdin.read),
    otherwise Python buffers the whole `ESC [ A` sequence and the follow-up
    select() sees an empty fd — making every arrow key look like a bare Esc.
    """
    ch = os.read(fd, 1)
    if ch == b"\x1b":                   # ESC — could be a sequence or bare Esc
        r, _, _ = select.select([fd], [], [], 0.03)
        if not r:
            return "ESC"
        rest = os.read(fd, 2)           # e.g. b"[A"
        if rest[:1] == b"[":
            code = chr(rest[1]) if len(rest) > 1 else ""
            return {"A": "UP", "B": "DOWN", "C": "RIGHT", "D": "LEFT",
                    "H": "HOME", "F": "END"}.get(code, "OTHER")
        return "ESC"
    if ch in (b"\r", b"\n"):
        return "ENTER"
    if ch in (b"\x7f", b"\b"):
        return "BACKSPACE"
    if ch == b"\x03":
        return "CTRL_C"
    try:
        return ch.decode("utf-8", "ignore")
    except Exception:
        return "OTHER"


def _draw(title: str, items: list[dict], filtered: list[int], sel: int,
          query: str, top: int, rows: int) -> None:
    w = ui.width()
    out = ["\x1b[H\x1b[2J"]            # home + clear

    out.append(ui.style(f"  {ui.G_BOT} {title}", ui.ACCENT, ui.BOLD) + "\r\n")
    out.append(ui.style(f"  ⌕ {query}", ui.ACCENT2)
               + ui.style("▏", ui.MUTE)
               + ui.style(f"   {len(filtered)} match" + ("es" if len(filtered) != 1 else ""),
                          ui.FAINT) + "\r\n\r\n")

    visible = filtered[top:top + rows]
    for vi, item_idx in enumerate(visible):
        real = top + vi
        label = items[item_idx]["label"]
        if len(label) > w - 6:
            label = label[:w - 7] + "…"
        if real == sel:
            out.append(ui.style(f" ▸ {label}", ui.BOT, ui.BOLD) + "\r\n")
        else:
            out.append(ui.style(f"   {label}", ui.MUTE) + "\r\n")

    # preview of the highlighted item
    if filtered:
        preview = items[filtered[sel]].get("preview")
        if preview:
            out.append("\r\n" + ui.style("  ── preview " + "─" * max(0, w - 14),
                                         ui.FAINT) + "\r\n")
            for ln in str(preview).splitlines()[:5]:
                out.append(ui.style("  " + ln[:w - 4], ui.FAINT) + "\r\n")

    out.append("\r\n" + ui.style(
        "  ↑↓ move · type to filter · enter open · esc cancel", ui.FAINT))
    sys.stdout.write("".join(out))
    sys.stdout.flush()


def choose(options: list[tuple[str, str]], title: str = "select") -> str | None:
    """Convenience over pick() for (value, description) pairs. Returns the
    chosen value, or None if cancelled."""
    items = [{"label": f"{val:18}{desc}", "value": val} for val, desc in options]
    idx = pick(items, title=title)
    return options[idx][0] if idx is not None else None


def pick(items: list[dict], title: str = "select",
         load_preview=None) -> int | None:
    """Show the picker. `load_preview(index)->str` lazily fills the preview for
    the highlighted row. Returns the chosen original index, or None."""
    if not (_HAS_TTY and sys.stdin.isatty() and sys.stdout.isatty()) or not items:
        return None

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    sel = 0
    query = ""
    rows = max(3, ui.height() - 10)
    _preview_cache: dict[int, str] = {}

    try:
        tty.setraw(fd)
        sys.stdout.write("\x1b[?1049h\x1b[?25l")     # alt screen, hide cursor
        while True:
            filtered = [i for i, it in enumerate(items)
                        if query.lower() in it["label"].lower()]
            if not filtered:
                sel = 0
            else:
                sel = max(0, min(sel, len(filtered) - 1))
                # lazily fetch the highlighted preview
                oi = filtered[sel]
                if load_preview and oi not in _preview_cache:
                    _preview_cache[oi] = load_preview(oi) or ""
                    items[oi]["preview"] = _preview_cache[oi]
            top = max(0, min(sel - rows // 2, max(0, len(filtered) - rows)))

            _draw(title, items, filtered, sel, query, top, rows)

            key = _read_key(fd)
            if key in ("ESC", "CTRL_C"):
                return None
            if key == "ENTER":
                return filtered[sel] if filtered else None
            if key == "UP":
                sel -= 1
            elif key == "DOWN":
                sel += 1
            elif key == "HOME":
                sel = 0
            elif key == "END":
                sel = len(filtered) - 1
            elif key == "BACKSPACE":
                query = query[:-1]; sel = 0
            elif len(key) == 1 and key.isprintable():
                query += key; sel = 0
            if filtered:
                sel = max(0, min(sel, len(filtered) - 1))
    finally:
        sys.stdout.write("\x1b[?25h\x1b[?1049l")     # restore cursor + screen
        sys.stdout.flush()
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
