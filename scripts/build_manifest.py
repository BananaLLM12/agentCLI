#!/usr/bin/env python3
"""Regenerate the source-integrity manifest.

Run after ANY legitimate change to the agentcli source:

    python3 scripts/build_manifest.py

It writes agentcli/MANIFEST.sha256 and prints the new ROOT_HASH, which you then
paste into agentcli/integrity.py (the ROOT_HASH constant). Committing both makes
that build tamper-evident: editing a source file in place afterward will be
detected on the next launch unless the manifest and ROOT_HASH are also updated.
"""
import hashlib
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agentcli import integrity  # noqa: E402


def main() -> None:
    manifest = integrity.build_manifest()
    with open(integrity.manifest_path(), "w", encoding="utf-8") as f:
        f.write(manifest)
    root = hashlib.sha256(manifest.encode()).hexdigest()

    # auto-patch ROOT_HASH in integrity.py so it's one command
    ipath = os.path.join(os.path.dirname(integrity.__file__), "integrity.py")
    src = open(ipath, "r", encoding="utf-8").read()
    src = re.sub(r'ROOT_HASH = "[0-9a-f]*"', f'ROOT_HASH = "{root}"', src, count=1)
    open(ipath, "w", encoding="utf-8").write(src)

    files = len(manifest.strip().splitlines())
    print(f"wrote {integrity.manifest_path()} ({files} files)")
    print(f"ROOT_HASH set to {root}")


if __name__ == "__main__":
    main()
