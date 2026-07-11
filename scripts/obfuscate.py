#!/usr/bin/env python3
"""Produce a SOURCELESS (bytecode-only) build of agentcli.

Compiles every module to a `.pyc` and drops the `.py`, so the shipped package
has no readable source to casually edit — you can't just open `integrity.py` and
comment out the check, because there is no `integrity.py`. Output goes to
`build_obf/agentcli/`.

Honest scope (read this): bytecode is NOT encryption. A determined reverser can
decompile `.pyc` back to rough source. What this buys you is a much higher bar
against *casual* tampering, layered on top of the integrity manifest. For
genuinely hard-to-reverse builds, compile to a native binary with Nuitka
(`nuitka --onefile`, compiles to C) or freeze with PyInstaller — see the note
this script prints at the end.

Usage:
    python3 scripts/build_manifest.py     # stamp integrity first
    python3 scripts/obfuscate.py
    PYTHONPATH=build_obf python3 -m agentcli --help
"""
import hashlib
import os
import py_compile
import re
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "agentcli")
OUT = os.path.join(ROOT, "build_obf", "agentcli")
sys.path.insert(0, ROOT)


def _compile(src_py: str, cfile: str) -> None:
    py_compile.compile(
        src_py, cfile=cfile, doraise=True,
        invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)


def main() -> None:
    from agentcli import integrity

    if os.path.exists(os.path.dirname(OUT)):
        shutil.rmtree(os.path.dirname(OUT))
    os.makedirs(OUT, exist_ok=True)

    compiled = 0
    for dirpath, _, files in os.walk(SRC):
        rel = os.path.relpath(dirpath, SRC)
        dst_dir = OUT if rel == "." else os.path.join(OUT, rel)
        os.makedirs(dst_dir, exist_ok=True)
        for fn in files:
            src = os.path.join(dirpath, fn)
            if fn.endswith(".py"):
                _compile(src, os.path.join(dst_dir, fn + "c"))   # e.g. cli.pyc
                compiled += 1
            elif not fn.endswith((".pyc", ".sha256")):
                shutil.copy2(src, os.path.join(dst_dir, fn))

    # regenerate the manifest over the BYTECODE build (excludes integrity.*)
    manifest = integrity.build_manifest(OUT)
    root = hashlib.sha256(manifest.encode()).hexdigest()

    # recompile integrity with the bytecode-build ROOT_HASH, WITHOUT touching
    # the source tree (integrity is excluded from the manifest, so this is safe)
    isrc = open(os.path.join(SRC, "integrity.py"), "r", encoding="utf-8").read()
    isrc = re.sub(r'ROOT_HASH = "[0-9a-f]*"', f'ROOT_HASH = "{root}"', isrc, 1)
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as tf:
        tf.write(isrc); tmp = tf.name
    _compile(tmp, os.path.join(OUT, "integrity.pyc"))
    os.unlink(tmp)
    open(os.path.join(OUT, "MANIFEST.sha256"), "w", encoding="utf-8").write(manifest)

    print(f"compiled {compiled} modules -> {OUT}")
    print(f"bytecode manifest ROOT_HASH: {root}")
    print(f"python version lock: {sys.version_info.major}.{sys.version_info.minor} "
          f"(sourceless .pyc is version-specific)")
    print()
    print("test it:   PYTHONPATH=build_obf python3 -m agentcli --help")
    print("stronger:  pip install nuitka && "
          "python3 -m nuitka --onefile --output-dir=build_bin agentcli/__main__.py")


if __name__ == "__main__":
    main()
