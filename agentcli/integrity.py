"""Source integrity — tamper-evidence for the CLI's own code.

At startup the CLI hashes every core source file and compares against a signed
manifest shipped in the package (MANIFEST.sha256). If a security-critical file
(guard, policy, permissions, intent, agent, tools…) has been modified, the CLI
notices: it warns, and if the operating policy is locked it refuses to run.

Honest scope: this is tamper-EVIDENCE, not DRM. Anyone who can edit this file
can disable the check — self-verification can't defend against an attacker who
already owns the filesystem. What it DOES give you: a locked, shipped build
can't be quietly patched (to weaken the guard, unlock the policy, exfiltrate
keys…) without the change being detected on the next launch. Regenerating the
manifest requires the build script AND updating ROOT_HASH below, so a casual
edit-in-place is caught.
"""
from __future__ import annotations

import hashlib
import os

_PKG = os.path.dirname(os.path.abspath(__file__))
_SELF = os.path.basename(__file__)              # this verifier is not self-listed
_MANIFEST = "MANIFEST.sha256"

# sha256 of MANIFEST.sha256's contents. Regenerate with scripts/build_manifest.py
# after any legitimate source change, then paste the new value here.
ROOT_HASH = "c28168e77b5af2f83c0ec245ae3667fb8d915c399d8219f90614d6f99e9fdcbf"

# files whose modification is security-critical (a subset, for reporting)
CRITICAL = {"guard.py", "policy_file.py", "permissions.py", "intent.py",
            "agent.py", "tools.py", "redact.py"}


def _rel_py_files() -> list[str]:
    out = []
    for root, _, files in os.walk(_PKG):
        for fn in files:
            if fn.endswith(".py"):
                rel = os.path.relpath(os.path.join(root, fn), _PKG)
                if rel != _SELF:
                    out.append(rel)
    return sorted(out)


def _hash(rel: str) -> str:
    with open(os.path.join(_PKG, rel), "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def build_manifest() -> str:
    return "".join(f"{_hash(r)}  {r}\n" for r in _rel_py_files())


def manifest_path() -> str:
    return os.path.join(_PKG, _MANIFEST)


def verify() -> dict:
    """Check every listed file against the manifest and the manifest against
    ROOT_HASH. Returns a status dict; ok=True in dev mode (no manifest)."""
    mp = manifest_path()
    if not os.path.exists(mp):
        return {"ok": True, "dev": True, "tampered": [], "missing": [],
                "root_ok": True}
    manifest = open(mp, "r", encoding="utf-8").read()
    root_ok = (not ROOT_HASH) or \
        hashlib.sha256(manifest.encode()).hexdigest() == ROOT_HASH

    expected = {}
    for line in manifest.splitlines():
        line = line.strip()
        if line:
            h, rel = line.split("  ", 1)
            expected[rel] = h

    tampered, missing = [], []
    for rel, h in expected.items():
        p = os.path.join(_PKG, rel)
        if not os.path.exists(p):
            missing.append(rel)
        elif _hash(rel) != h:
            tampered.append(rel)

    ok = root_ok and not tampered and not missing
    return {"ok": ok, "dev": False, "root_ok": root_ok,
            "tampered": sorted(tampered), "missing": sorted(missing)}


def status_line() -> str:
    r = verify()
    if r.get("dev"):
        return "unverified (dev checkout — no manifest)"
    if r["ok"]:
        return "verified ✓ (all source hashes match)"
    bits = []
    if not r["root_ok"]:
        bits.append("manifest root mismatch")
    if r["tampered"]:
        crit = [f for f in r["tampered"] if os.path.basename(f) in CRITICAL]
        bits.append(f"MODIFIED: {', '.join(r['tampered'])}"
                    + (" (security-critical!)" if crit else ""))
    if r["missing"]:
        bits.append(f"missing: {', '.join(r['missing'])}")
    return "TAMPERED ✗ — " + " · ".join(bits)
