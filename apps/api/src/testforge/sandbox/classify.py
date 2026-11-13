"""Which limit a run crossed, decided from the sandbox's measurements.

The order matters (the CodeJudge verdict order): output first, because once a write is
cut at RLIMIT_FSIZE a runtime may spin or fail in other ways that look like a timeout;
then the wall clock and CPU time; then memory; then processes. A run with no limit crossed
returns None, whatever its exit status (failing tests are not a limit).
"""

from __future__ import annotations

import signal
from dataclasses import dataclass

from testforge.sandbox.protocol import Limit

OOM_MARKERS = (
    b"MemoryError",
    b"heap out of memory",
    b"JavaScript heap out of memory",
    b"Cannot allocate memory",
    b"ERR_WORKER_OUT_OF_MEMORY",
    b"std::bad_alloc",
)
OUTPUT_MARKERS = (b"File too large", b"EFBIG", b"SIGXFSZ")
PROCESS_MARKERS = (
    b"BlockingIOError: [Errno 11] Resource temporarily unavailable",
    b"can't start new thread",
    b"EAGAIN",
    b"spawn EAGAIN",
    b"fork: retry",
)
CPU_MARKERS = (b"SIGXCPU",)


@dataclass(frozen=True)
class Measured:
    exit_code: int | None
    signal: int | None
    cpu_ms: int
    wall_ms: int
    memory_kb: int
    stdout_bytes: int
    stderr_bytes: int
    wall_timed_out: bool
    # stderr and stdout tails plus the runner's report text, searched for markers.
    text: bytes


@dataclass(frozen=True)
class Budget:
    cpu_ms: int
    wall_ms: int
    memory_mb: int
    output_bytes: int
    memory_overhead_mb: int
    rss_mode: bool


def classify(m: Measured, b: Budget) -> tuple[Limit | None, str]:
    """The limit crossed and a plain-language detail, or (None, "")."""
    at_cap = max(m.stdout_bytes, m.stderr_bytes) >= b.output_bytes
    if at_cap or m.signal == signal.SIGXFSZ or any(x in m.text for x in OUTPUT_MARKERS):
        return "output", (
            f"The tests wrote more than the {_bytes(b.output_bytes)} output limit; "
            "writes past it were refused and the run was stopped"
        )
    if m.wall_timed_out:
        return "wall_clock", (
            f"The run was still going after the {b.wall_ms // 1000} s wall clock limit "
            "(a test that sleeps, waits or loops forever) and was stopped"
        )
    if m.cpu_ms > b.cpu_ms or m.signal == signal.SIGXCPU or any(x in m.text for x in CPU_MARKERS):
        return "cpu", (
            f"The tests used {m.cpu_ms / 1000:.1f} s of CPU time, over the "
            f"{b.cpu_ms // 1000} s limit, and were stopped"
        )
    limit_kb = b.memory_mb * 1024
    oom = any(x in m.text for x in OOM_MARKERS)
    over_rss = b.rss_mode and m.memory_kb > (b.memory_mb + b.memory_overhead_mb) * 1024
    killed = m.signal == signal.SIGKILL and m.memory_kb >= limit_kb * 0.9
    if oom or over_rss or killed:
        return "memory", (
            f"The tests tried to use more than the {b.memory_mb} MB memory limit "
            f"(peak resident {m.memory_kb // 1024} MB); the allocation was refused"
        )
    if any(x in m.text for x in PROCESS_MARKERS):
        return "processes", (
            "The tests tried to start more processes or threads than the sandbox allows; "
            "the extra ones were refused"
        )
    return None, ""


def _bytes(n: int) -> str:
    if n >= 1 << 20:
        return f"{n / (1 << 20):.0f} MB"
    return f"{n / 1024:.0f} KB"
