"""Terminal styling — a small, cohesive theme built on raw ANSI (no deps).

Truecolor (24-bit) where available, auto-disabled when output isn't a TTY or
NO_COLOR is set. Everything the CLI prints goes through here so the look stays
consistent.
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import threading
import time

# ---- capability detection -------------------------------------------------
_ENABLED = (sys.stdout.isatty() and os.environ.get("NO_COLOR") is None
            and os.environ.get("TERM") != "dumb")


def _rgb(r: int, g: int, b: int) -> str:
    return f"\033[38;2;{r};{g};{b}m" if _ENABLED else ""


def _bg(r: int, g: int, b: int) -> str:
    return f"\033[48;2;{r};{g};{b}m" if _ENABLED else ""


# ---- palette (soft violet/cyan accent set) --------------------------------
RESET  = "\033[0m" if _ENABLED else ""
BOLD   = "\033[1m" if _ENABLED else ""
DIMSTY = "\033[2m" if _ENABLED else ""
ITAL   = "\033[3m" if _ENABLED else ""

ACCENT = _rgb(167, 139, 250)   # violet — brand accent
ACCENT2 = _rgb(96, 205, 255)   # cyan — secondary
USER   = _rgb(125, 211, 252)   # sky blue — the human
BOT    = _rgb(134, 239, 172)   # mint — the model
TOOL   = _rgb(250, 204, 21)    # amber — tool activity
ERRC   = _rgb(248, 113, 113)   # red — errors
MUTE   = _rgb(120, 125, 140)   # muted gray — meta/hints
FAINT  = _rgb(90, 95, 110)     # fainter still

# ---- glyphs ---------------------------------------------------------------
G_PROMPT = "❯"
G_BOT    = "◆"
G_TOOL   = "▸"
G_BRANCH = "╰─"
G_OK     = "✔"
G_ERR    = "✗"
G_RETRY  = "↻"
G_DOT    = "•"


def width() -> int:
    return shutil.get_terminal_size((80, 24)).columns


def height() -> int:
    return shutil.get_terminal_size((80, 24)).lines


def style(text: str, *codes: str) -> str:
    if not _ENABLED:
        return text
    return "".join(codes) + text + RESET


# ---- components -----------------------------------------------------------
def _boxed(rows: list[list[tuple[str, tuple]]]) -> str:
    """Render a rounded box. Each row is a list of (text, style-codes) spans;
    padding is computed from visible text only so escape codes never break it.
    """
    visibles = ["".join(t for t, _ in row) for row in rows]
    inner = min(max(len(v) for v in visibles) + 3, width() - 2)
    out = [style("╭" + "─" * inner + "╮", ACCENT)]
    for row, vis in zip(rows, visibles):
        painted = "".join(style(t, *c) for t, c in row)
        pad = " " * max(0, inner - len(vis) - 1)
        out.append(style("│", ACCENT) + " " + painted + pad + style("│", ACCENT))
    out.append(style("╰" + "─" * inner + "╯", ACCENT))
    return "\n".join(out)


ACCENT_RGB = (167, 139, 250)
CYAN_RGB = (96, 205, 255)


def _lerp(a: int, b: int, t: float) -> int:
    return int(a + (b - a) * t)


def gradient(text: str, c1=ACCENT_RGB, c2=CYAN_RGB, bold: bool = False) -> str:
    """Color a string character-by-character across an RGB gradient."""
    if not _ENABLED or not text:
        return text
    n = max(1, len(text) - 1)
    b = BOLD if bold else ""
    out = []
    for i, ch in enumerate(text):
        t = i / n
        out.append(_rgb(_lerp(c1[0], c2[0], t), _lerp(c1[1], c2[1], t),
                        _lerp(c1[2], c2[2], t)) + b + ch)
    return "".join(out) + RESET


def logo(version: str = "1.0", subtitle: str = "multi-provider terminal agent") -> str:
    """The wordmark — a gradient-lettered identity block."""
    mark = "a g e n t c l i"
    lines = [
        "  " + gradient("◈", ACCENT_RGB, ACCENT_RGB) + "  "
        + gradient(mark, bold=True) + "   " + style("v" + version, FAINT),
        "     " + gradient("▔" * len(mark)),
        "     " + style(subtitle, MUTE),
    ]
    return "\n".join(lines)


_MODE_COLOR = {"read-only": ACCENT2, "approve": TOOL, "auto": ERRC}
_MODE_GLYPH = {"read-only": "◔", "approve": "◑", "auto": "●"}


def mode_badge(mode: str) -> str:
    key = mode.split(" ")[0]
    c = _MODE_COLOR.get(key, MUTE)
    return style(f"{_MODE_GLYPH.get(key, '○')} {key}", c, BOLD)


def status_bar(provider: str, model: str, mode: str, thread: str,
               tokens: int, persona: bool, render: bool, stream: bool,
               tools: int) -> str:
    """A single dense line summarizing the live session state."""
    sep = style("  ·  ", FAINT)
    seg = [
        mode_badge(mode),
        style(f"{provider}:{model}", ACCENT2),
        style(f"⌥ {thread}", BOT),
        style(f"{tokens} tok", MUTE),
        style(f"{tools} tools", MUTE),
    ]
    if persona:
        seg.append(style("persona", TOOL))
    seg.append(style("md" if render else "raw", FAINT))
    seg.append(style("stream" if stream else "block", FAINT))
    return "  " + sep.join(seg)


def banner(provider: str, model: str, tokens: int, resumed: int = 0,
           mode: str = "") -> str:
    """A rounded header box announcing the session."""
    meta = f"{tokens} tokens" + (f"  ·  resumed {resumed} msgs" if resumed else "")
    rows = [
        [(f"{G_BOT} ", (ACCENT,)), ("agentcli", (BOLD,)),
         ("   ", ()), (provider, (ACCENT2,)), (" · ", (FAINT,)), (model, (BOT,))],
        [(meta, (MUTE,))],
    ]
    if mode:
        mc = _MODE_COLOR.get(mode.split(" ")[0], MUTE)
        rows.append([("mode ", (FAINT,)), (mode, (mc, BOLD))])
    return _boxed(rows)


def notify_banner(title: str, message: str, status: str = "done") -> str:
    """A rounded, status-colored banner announcing task completion."""
    palette = {
        "done":    (BOT, G_OK, "done"),
        "blocked": (TOOL, "⚑", "blocked"),
        "failed":  (ERRC, G_ERR, "failed"),
    }
    color, glyph, label = palette.get(status, palette["done"])

    # temporarily borrow the accent color for the frame
    def framed(rows):
        visibles = ["".join(t for t, _ in row) for row in rows]
        inner = min(max(len(v) for v in visibles) + 3, width() - 2)
        out = [style("╭" + "─" * inner + "╮", color)]
        for row, vis in zip(rows, visibles):
            painted = "".join(style(t, *c) for t, c in row)
            pad = " " * max(0, inner - len(vis) - 1)
            out.append(style("│", color) + " " + painted + pad + style("│", color))
        out.append(style("╰" + "─" * inner + "╯", color))
        return "\n".join(out)

    return framed([
        [(f"{glyph} ", (color, BOLD)), (title, (BOLD,)),
         ("  ", ()), (label, (color,))],
        [(message[:60], (MUTE,))],
    ])


def approval(tool: str, detail: str) -> str:
    """The line shown when the agent asks permission to run something."""
    return (f"  {style('needs approval', TOOL, BOLD)} "
            f"{style(tool, TOOL)} {style(detail, MUTE)}")


def denied_line(text: str) -> str:
    return f"  {style('⊘ ' + text, ERRC)}"


_ANSI_RE = re.compile(r"(\x1b\[[0-9;]*m)")


def rl_safe(s: str) -> str:
    """Wrap ANSI escapes in \\001..\\002 so readline excludes them from its
    prompt-width math (otherwise the cursor/editing gets misaligned)."""
    if not _ENABLED:
        return s
    return _ANSI_RE.sub("\x01\\1\x02", s)


def prompt(mode: str = "") -> str:
    """The input caret, colored by the active permission mode so the CLI's
    'mood' (how much it can do on its own) is always visible."""
    c = _MODE_COLOR.get(mode.split(" ")[0], ACCENT)
    return f"{style(G_PROMPT, c, BOLD)} "


def dashboard(rows: list[tuple[str, str]], title: str = "status") -> str:
    """A labeled, boxed key/value panel for /status."""
    label_w = max(len(k) for k, _ in rows)
    body = [[(f"{k.ljust(label_w)}  ", (FAINT,)), (str(v), (ACCENT2,))]
            for k, v in rows]
    header = [[(f"{G_BOT} ", (ACCENT,)), (title, (BOLD,))]]
    return _boxed(header + [[("", ())]] + body)


def bot_label() -> str:
    return f"{style(G_BOT, BOT)} "


def format_action(name: str, args: dict):
    """A clean, human-readable one-liner for a tool call: (glyph, color, text)."""
    a = args or {}
    def g(k, d=""): return str(a.get(k, d))

    if name in ("run_shell", "run_background"):
        pre = "bg: " if name == "run_background" else ""
        return ("❯", TOOL, pre + g("command"))
    if name == "write_file":
        return ("✎", BOT, f"write {g('path')}  ({len(g('content'))} chars)")
    if name == "edit_file":
        return ("✎", BOT, f"edit {g('path')}")
    if name == "replace_lines":
        return ("✎", BOT, f"edit {g('path')} · lines {g('start')}-{g('end')}")
    if name == "insert_lines":
        return ("✎", BOT, f"insert into {g('path')} @ {g('after_line')}")
    if name == "append_file":
        return ("✎", BOT, f"append {g('path')}")
    if name == "make_dir":
        return ("✎", BOT, f"mkdir {g('path')}")
    if name == "delete_path":
        return ("✖", ERRC, f"delete {g('path')}")
    if name in ("move_path", "copy_path"):
        verb = "move" if name == "move_path" else "copy"
        return ("✎", BOT, f"{verb} {g('src')} → {g('dst')}")
    if name in ("read_file", "read_lines"):
        return ("◎", ACCENT2, f"read {g('path')}")
    if name == "list_dir":
        return ("◎", ACCENT2, f"ls {g('path', '.')}")
    if name == "find_files":
        return ("⌕", ACCENT2, f"find {g('pattern')}")
    if name == "search_text":
        return ("⌕", ACCENT2, f"grep {g('pattern')}")
    if name == "web_search":
        return ("⌕", ACCENT2, f"search \"{g('query')}\"")
    if name == "http_get":
        return ("↯", ACCENT2, f"GET {g('url')}")
    if name == "http_post":
        return ("↯", ACCENT2, f"POST {g('url')}")
    if name == "check_job":
        return ("◎", ACCENT2, f"check job {g('job_id')}")
    if name == "create_plan":
        return ("◆", ACCENT, f"draft plan · {len(a.get('steps', []))} steps")
    if name == "update_plan":
        return ("◆", ACCENT, f"plan step {g('step')} → {g('status')}")
    if name == "spawn_agent":
        return ("⤷", ACCENT, f"sub-agent · {g('task')[:44]}")
    if name == "notify":
        return ("◆", BOT, f"notify · {g('title')}")
    if name == "lock_session":
        return ("🔒", ERRC, "lock session")
    kv = ", ".join(f"{k}={str(v)[:24]}" for k, v in a.items())
    return ("▸", MUTE, f"{name}({kv})")


def action_line(name: str, args: dict) -> str:
    glyph, color, summary = format_action(name, args)
    cap = width() - 6
    if len(summary) > cap:
        summary = summary[:cap - 1] + "…"
    return "  " + style(f"{glyph} {summary}", color)


def action_result(result: str) -> str:
    """Render a tool result under its action, with a pass/fail glyph."""
    low = result.lstrip()[:40].lower()
    err = (low.startswith(("error", "[")) or "denied" in low or "not found" in low
           or "timed out" in low or "no such" in low)
    lines = result.splitlines() or [""]
    head = lines[0].strip() or "(no output)"
    cap = width() - 10
    if len(head) > cap:
        head = head[:cap - 1] + "…"
    more = f"  (+{len(lines) - 1} more)" if len(lines) > 1 else ""
    glyph = "✗" if err else "✓"
    gc = ERRC if err else BOT
    return "    " + style(glyph, gc) + " " + style(head + more, ERRC if err else FAINT)


def retry_line(text: str) -> str:
    return f"  {style(G_RETRY + ' ' + text, MUTE, ITAL)}"


def error_line(text: str) -> str:
    return f"{style(' ' + G_ERR + ' ', ERRC, BOLD)}{style(text, ERRC)}"


def hint(text: str) -> str:
    return style(text, MUTE)


def rule() -> str:
    return style("─" * min(width(), 60), FAINT)


class Spinner:
    """A tiny threaded spinner for non-streaming waits."""
    FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, label: str = "thinking"):
        self.label = label
        self._stop = threading.Event()
        self._t: threading.Thread | None = None

    def __enter__(self):
        if _ENABLED:
            self._t = threading.Thread(target=self._spin, daemon=True)
            self._t.start()
        return self

    def _spin(self):
        i = 0
        while not self._stop.is_set():
            f = self.FRAMES[i % len(self.FRAMES)]
            sys.stderr.write(f"\r{style(f, ACCENT)} {style(self.label, MUTE)}")
            sys.stderr.flush()
            i += 1
            time.sleep(0.08)

    def __exit__(self, *a):
        self._stop.set()
        if self._t:
            self._t.join()
        if _ENABLED:
            sys.stderr.write("\r" + " " * (len(self.label) + 4) + "\r")
            sys.stderr.flush()
