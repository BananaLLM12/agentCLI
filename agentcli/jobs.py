"""Background jobs — run long shell commands without blocking the agent.

The model starts a command with run_background (returns a job id immediately),
keeps working, and later calls check_job to see if it finished and read its
output. Output streams to a temp file so it survives between checks.
"""
from __future__ import annotations

import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass, field


@dataclass
class Job:
    id: str
    command: str
    proc: subprocess.Popen
    outfile: str
    started: float = field(default_factory=time.time)


JOBS: dict[str, Job] = {}


def start(command: str) -> str:
    from . import config, sandbox
    jid = uuid.uuid4().hex[:6]
    f = tempfile.NamedTemporaryFile(prefix=f"agentcli-job-{jid}-",
                                    suffix=".log", delete=False)
    mode = config.load().get("sandbox_mode", "workspace")
    argv, _ = sandbox.wrap(command, mode)
    proc = subprocess.Popen(argv, stdout=f, stderr=subprocess.STDOUT, text=True)
    JOBS[jid] = Job(jid, command, proc, f.name)
    return jid


def _read(path: str, tail: int = 3000) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            data = fh.read()
        return data[-tail:] if len(data) > tail else data
    except OSError:
        return ""


def check(jid: str) -> dict:
    j = JOBS.get(jid)
    if not j:
        return {"found": False}
    rc = j.proc.poll()
    return {
        "found": True,
        "running": rc is None,
        "exit_code": rc,
        "elapsed": round(time.time() - j.started, 1),
        "output": _read(j.outfile),
        "command": j.command,
    }


def listing() -> list[tuple[str, str, str, float]]:
    out = []
    for j in JOBS.values():
        rc = j.proc.poll()
        status = "running" if rc is None else f"exit {rc}"
        out.append((j.id, status, j.command, round(time.time() - j.started, 1)))
    return out


def running() -> int:
    return sum(1 for j in JOBS.values() if j.proc.poll() is None)
