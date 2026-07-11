"""OS-level sandboxing for shell execution — kernel-enforced, not in-process.

This is the layer that survives a compromised model: even if the guard is
bypassed and the model runs arbitrary shell, the KERNEL confines it. On macOS
we use Seatbelt (`sandbox-exec`); on Linux, bubblewrap (`bwrap`) if available.

Modes:
  off        no sandbox (raw shell)
  workspace  writes restricted to the working dir + temp; network allowed
             (default — stops "write outside the project" without breaking
             npm/pip/git which need the network)
  strict     workspace + NO network (blocks exfiltration entirely)

Unlike the permission policy (which the model could theoretically talk its way
around), a kernel sandbox can't be escaped by the process it confines.
"""
from __future__ import annotations

import os
import platform
import shutil

DEPRECATION = "sandbox-exec: The sandbox-exec command is deprecated"


def backend() -> str | None:
    if platform.system() == "Darwin" and shutil.which("sandbox-exec"):
        return "seatbelt"
    if platform.system() == "Linux" and shutil.which("bwrap"):
        return "bwrap"
    return None


def available() -> bool:
    return backend() is not None


def _seatbelt_profile(workdir: str, allow_network: bool) -> str:
    wd = os.path.realpath(workdir)
    net = "" if allow_network else "(deny network*)\n"
    return f"""(version 1)
(allow default)
{net}(deny file-write*)
(allow file-write*
    (subpath "{wd}")
    (subpath "/private/tmp")
    (subpath "/tmp")
    (subpath "/private/var/folders")
    (literal "/dev/null")
    (literal "/dev/stdout")
    (literal "/dev/stderr")
    (regex #"^/dev/tty"))
"""


def wrap(command: str, mode: str = "workspace",
         workdir: str | None = None) -> tuple[list[str], bool]:
    """Return (argv, sandboxed?) to execute `command`. Falls back to a plain
    shell (sandboxed=False) when no backend is available or mode is off."""
    workdir = workdir or os.getcwd()
    b = backend()
    if mode == "off" or b is None:
        return (["/bin/sh", "-c", command], False)

    allow_net = mode != "strict"
    if b == "seatbelt":
        prof = _seatbelt_profile(workdir, allow_net)
        return (["sandbox-exec", "-p", prof, "/bin/sh", "-c", command], True)

    if b == "bwrap":
        argv = ["bwrap", "--ro-bind", "/", "/", "--dev", "/dev",
                "--tmpfs", "/tmp", "--bind", workdir, workdir,
                "--chdir", workdir, "--die-with-parent"]
        if not allow_net:
            argv.append("--unshare-net")
        argv += ["/bin/sh", "-c", command]
        return (argv, True)
    return (["/bin/sh", "-c", command], False)


def clean_output(text: str) -> str:
    """Strip the harmless sandbox-exec deprecation warning from output."""
    if DEPRECATION in text:
        text = "\n".join(l for l in text.splitlines() if DEPRECATION not in l)
    return text
