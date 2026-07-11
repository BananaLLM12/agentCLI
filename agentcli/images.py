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


def load(path: str) -> Image | None:
    path = os.path.expanduser(path)
    mime = mime_for(path)
    if not mime or not os.path.isfile(path):
        return None
    with open(path, "rb") as f:
        return Image(data=f.read(), mime=mime)


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
