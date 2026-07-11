"""Lightweight Markdown -> ANSI renderer for the terminal.

Not a full CommonMark implementation — just the things an assistant actually
emits: headers, bold/italic, inline code, fenced code blocks, bullet and
numbered lists, blockquotes, and horizontal rules. Everything routes through
the shared `ui` palette so it matches the rest of the CLI.
"""
from __future__ import annotations

import re

from . import ui

_BOLD = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
_ITAL = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)|(?<!_)_(?!_)(.+?)_")
_CODE = re.compile(r"`([^`]+)`")


def _inline(text: str) -> str:
    """Apply inline spans: `code`, **bold**, *italic*. No background fills —
    just color, so it never smears a highlighter block across the line."""
    text = _CODE.sub(lambda m: ui.style(m.group(1), ui.ACCENT2, ui.BOLD), text)
    text = _BOLD.sub(lambda m: ui.style(m.group(1) or m.group(2), ui.BOLD), text)
    text = _ITAL.sub(lambda m: ui.style(m.group(1) or m.group(2), ui.ITAL), text)
    return text


def _code_block(lines: list[str], lang: str) -> list[str]:
    """Render a fenced code block as a bordered, tinted panel."""
    w = min(max((len(l) for l in lines), default=0), ui.width() - 4)
    out = [ui.style("  ┌" + "─" * (w + 2) + "┐", ui.FAINT)]
    if lang:
        out[0] = ui.style("  ┌─ " + lang + " " + "─" * max(0, w - len(lang) - 1) + "┐",
                          ui.FAINT)
    for l in lines:
        pad = " " * max(0, w - len(l))
        out.append(ui.style("  │ ", ui.FAINT)
                   + ui.style(l + pad, ui.ACCENT2) + ui.style(" │", ui.FAINT))
    out.append(ui.style("  └" + "─" * (w + 2) + "┘", ui.FAINT))
    return out


def render(md: str) -> str:
    """Turn a Markdown string into styled terminal text."""
    if not ui._ENABLED:
        return md   # plain text when color is off (pipes, NO_COLOR)

    lines = md.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]

        # fenced code block
        m = re.match(r"^\s*```(\w*)\s*$", line)
        if m:
            lang = m.group(1)
            body = []
            i += 1
            while i < len(lines) and not re.match(r"^\s*```\s*$", lines[i]):
                body.append(lines[i]); i += 1
            out.extend(_code_block(body, lang))
            i += 1
            continue

        # headers
        h = re.match(r"^(#{1,6})\s+(.*)$", line)
        if h:
            level = len(h.group(1))
            txt = h.group(2)
            if level == 1:
                out.append(ui.style("▌ " + txt, ui.ACCENT, ui.BOLD))
            elif level == 2:
                out.append(ui.style("▍ " + txt, ui.ACCENT2, ui.BOLD))
            else:
                out.append(ui.style(txt, ui.BOLD))
            i += 1
            continue

        # horizontal rule
        if re.match(r"^\s*([-*_])\1{2,}\s*$", line):
            out.append(ui.rule()); i += 1; continue

        # blockquote
        q = re.match(r"^\s*>\s?(.*)$", line)
        if q:
            out.append(ui.style("┃ ", ui.FAINT) + ui.style(_inline(q.group(1)), ui.MUTE))
            i += 1; continue

        # bullet list
        b = re.match(r"^(\s*)[-*+]\s+(.*)$", line)
        if b:
            indent = b.group(1)
            out.append(indent + ui.style("• ", ui.ACCENT) + _inline(b.group(2)))
            i += 1; continue

        # numbered list
        n = re.match(r"^(\s*)(\d+)\.\s+(.*)$", line)
        if n:
            out.append(n.group(1) + ui.style(n.group(2) + ". ", ui.ACCENT)
                       + _inline(n.group(3)))
            i += 1; continue

        # plain paragraph line
        out.append(_inline(line))
        i += 1

    return "\n".join(out)
