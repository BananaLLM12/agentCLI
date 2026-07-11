"""Secure API-key storage via the OS keychain (no plaintext on disk).

On macOS this shells out to the built-in `security` tool to keep keys in the
login Keychain; on Linux it uses `secret-tool` (libsecret) if present. When no
keychain is available it reports so, and the caller falls back to the
0600 config file. No third-party dependencies.
"""
from __future__ import annotations

import platform
import shutil
import subprocess

_SERVICE = "agentcli"
_ACCOUNT = "agentcli"


def backend() -> str | None:
    if platform.system() == "Darwin" and shutil.which("security"):
        return "keychain"
    if platform.system() == "Linux" and shutil.which("secret-tool"):
        return "secret-tool"
    return None


def available() -> bool:
    return backend() is not None


def set_key(name: str, value: str) -> bool:
    b = backend()
    try:
        if b == "keychain":
            subprocess.run(
                ["security", "add-generic-password", "-a", _ACCOUNT,
                 "-s", f"{_SERVICE}-{name}", "-w", value, "-U"],
                capture_output=True, check=True, timeout=5)
            return True
        if b == "secret-tool":
            subprocess.run(
                ["secret-tool", "store", "--label", f"{_SERVICE}-{name}",
                 "service", _SERVICE, "account", name],
                input=value, text=True, capture_output=True, check=True, timeout=5)
            return True
    except Exception:
        return False
    return False


def get_key(name: str) -> str | None:
    b = backend()
    try:
        if b == "keychain":
            r = subprocess.run(
                ["security", "find-generic-password", "-a", _ACCOUNT,
                 "-s", f"{_SERVICE}-{name}", "-w"],
                capture_output=True, text=True, timeout=5)
            return r.stdout.strip() if r.returncode == 0 else None
        if b == "secret-tool":
            r = subprocess.run(
                ["secret-tool", "lookup", "service", _SERVICE, "account", name],
                capture_output=True, text=True, timeout=5)
            return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None
    return None


def delete_key(name: str) -> bool:
    b = backend()
    try:
        if b == "keychain":
            subprocess.run(
                ["security", "delete-generic-password", "-a", _ACCOUNT,
                 "-s", f"{_SERVICE}-{name}"], capture_output=True, timeout=5)
            return True
        if b == "secret-tool":
            subprocess.run(
                ["secret-tool", "clear", "service", _SERVICE, "account", name],
                capture_output=True, timeout=5)
            return True
    except Exception:
        return False
    return False
