"""Image handling for vision — detect image paths a user dragged into the
terminal, load them, and strip them out of the typed text.

Dragging a file into most terminals pastes its path, sometimes quoted or with
backslash-escaped spaces. We pull any image-looking path out of the line, load
the bytes, and hand back the cleaned text plus the images.
"""
from __future__ import annotations

import os
import re

from .types import Image

_EXTS = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
         ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp"}

# a path token: quoted, or unquoted with backslash-escaped spaces, ending in an
# image extension
_PATH_RE = re.compile(
    r"""'([^']+\.(?:png|jpe?g|gif|webp|bmp))'      # 'single quoted'
      | "([^"]+\.(?:png|jpe?g|gif|webp|bmp))"      # "double quoted"
      | ((?:[^\s\\]|\\.)+\.(?:png|jpe?g|gif|webp|bmp))  # bare / escaped-space
    """,
    re.IGNORECASE | re.VERBOSE)


def mime_for(path: str) -> str | None:
    return _EXTS.get(os.path.splitext(path)[1].lower())


def _normalize_path(path: str) -> str:
    """Handle the ways terminals hand over a dragged file: file:// URLs and
    %-encoding, plus ~ expansion and stray whitespace."""
    path = path.strip().strip("'\"")
    if path.startswith("file://"):
        from urllib.parse import unquote, urlparse
        path = unquote(urlparse(path).path)
    return os.path.expanduser(path)


def load(path: str) -> Image | None:
    path = _normalize_path(path)
    mime = mime_for(path)
    if not mime or not os.path.isfile(path):
        return None
    with open(path, "rb") as f:
        return Image(data=f.read(), mime=mime)


def dimensions(data: bytes) -> tuple[int, int] | None:
    """Best-effort (width, height) from image header bytes — no PIL needed."""
    import struct
    try:
        if data[:8] == b"\x89PNG\r\n\x1a\n":                     # PNG
            w, h = struct.unpack(">II", data[16:24]); return (w, h)
        if data[:3] == b"GIF":                                    # GIF
            w, h = struct.unpack("<HH", data[6:10]); return (w, h)
        if data[:2] == b"BM":                                     # BMP
            w, h = struct.unpack("<ii", data[18:26]); return (w, abs(h))
        if data[:2] == b"\xff\xd8":                               # JPEG
            i = 2
            while i < len(data) - 9:
                if data[i] != 0xFF:
                    i += 1; continue
                marker = data[i + 1]
                if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                    h, w = struct.unpack(">HH", data[i + 5:i + 9]); return (w, h)
                seg = struct.unpack(">H", data[i + 2:i + 4])[0]
                i += 2 + seg
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":         # WEBP (VP8X/VP8)
            if data[12:16] == b"VP8X":
                w = 1 + (data[24] | data[25] << 8 | data[26] << 16)
                h = 1 + (data[27] | data[28] << 8 | data[29] << 16)
                return (w, h)
    except Exception:
        return None
    return None


# images the model requested via inspect_image, awaiting attach to the next turn
PENDING: list[Image] = []


def queue(img: Image) -> None:
    PENDING.append(img)


def drain() -> list[Image]:
    out = list(PENDING)
    PENDING.clear()
    return out


def extract(text: str) -> tuple[str, list[Image]]:
    """Return (text_without_image_paths, [loaded images])."""
    images: list[Image] = []
    spans: list[tuple[int, int]] = []
    for m in _PATH_RE.finditer(text):
        raw = m.group(1) or m.group(2) or m.group(3)
        path = raw.replace("\\ ", " ").replace("\\", "")
        img = load(path)
        if img:
            images.append(img)
            spans.append((m.start(), m.end()))
    if not spans:
        return text, []
    # remove matched path spans from the text, back to front
    for s, e in reversed(spans):
        text = text[:s] + text[e:]
    return re.sub(r"\s{2,}", " ", text).strip(), images
