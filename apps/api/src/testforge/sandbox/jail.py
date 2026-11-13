"""Run one test suite in an nsjail sandbox and measure it.

This is Euron Open CodeJudge's unprivileged sandbox design, reused for test runs. Each run
gets fresh user, PID, network, mount, IPC and UTS namespaces: it runs as uid 65534 with
no network interfaces (a loopback at most, no route anywhere), sees read-only system
directories and the read-only test toolchain, its own workspace and a small private
``/tmp``, and nothing else (no other run's workspace, no service code, no secret).
rlimits cap CPU time, address space, processes, file size (output) and open files; a wall
clock limit catches tests that sleep or hang; a syscall filter refuses namespace, mount,
ptrace, bpf, keyring, perf and io_uring calls. The sandboxed process is the first thing
the kernel kills when the container runs out of memory.

Limits come from rlimits, not cgroups: cgroups would need a privileged or cgroup-delegated
container, and the point of this design is that the sandbox container has no privileges
(docs/architecture/sandbox.md). CPU time and peak memory come from ``wait4``, which counts
every process in the sandbox.
"""

from __future__ import annotations

import contextlib
import math
import os
import signal
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

# System directories a run may read. Missing ones are skipped (lib64 is absent on arm64).
# Deliberately absent: /etc (no passwd, no hosts, no resolv.conf), /proc, /sys, /opt/venv
# (the service), /var, /home, /root.
READ_ONLY = (
    "/usr",
    "/lib",
    "/lib64",
    "/bin",
    "/etc/alternatives",
    "/etc/ld.so.cache",
    "/dev/null",
    "/dev/zero",
    "/dev/urandom",
)

# Refused inside the sandbox even though the outer container allows some of them (nsjail
# needs them to build the sandbox; a test never does). clone3 fails with ENOSYS so the C
# library falls back to clone, which threads still need.
POLICY = (
    "POLICY testforge {"
    " ERRNO(38) { clone3 },"
    " ERRNO(1) { unshare, setns, mount, umount, pivot_root, chroot, ptrace, process_vm_readv,"
    " process_vm_writev, bpf, keyctl, add_key, request_key, perf_event_open, userfaultfd,"
    " io_uring_setup, io_uring_enter, io_uring_register, kexec_load, init_module,"
    " finit_module, delete_module, swapon, swapoff, reboot, acct, open_by_handle_at,"
    " name_to_handle_at, quotactl, syslog, settimeofday, clock_settime, clock_adjtime }"
    " } USE testforge DEFAULT ALLOW"
)

BASE_ENV = ("PATH=/usr/bin:/bin", "LANG=C.UTF-8", "HOME=/tmp", "TMPDIR=/tmp")


@dataclass(frozen=True)
class RunLimits:
    cpu_ms: int
    wall_ms: int
    # RLIMIT_AS in MB, or None for runtimes that reserve far more than they use (rss mode).
    address_mb: int | None
    output_bytes: int
    processes: int = 64
    stack_mb: int = 64
    open_files: int = 256
    tmp_mb: int = 256
    # The run's environment ("NAME=value") on top of BASE_ENV; nothing else is inherited.
    env: tuple[str, ...] = ()


@dataclass
class RunResult:
    exit_code: int | None
    signal: int | None
    cpu_ms: int
    wall_ms: int
    memory_kb: int
    output_bytes: int
    wall_timed_out: bool
    launch_failed: bool = False
    log: str = ""

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and self.signal is None and not self.wall_timed_out


@dataclass
class Mount:
    source: Path
    target: str
    writable: bool = False


@dataclass
class Sandbox:
    nsjail: str = "/usr/local/bin/nsjail"
    read_only: tuple[str, ...] = field(
        default_factory=lambda: tuple(p for p in READ_ONLY if os.path.exists(p))
    )

    def command(
        self, argv: list[str], limits: RunLimits, mounts: list[Mount], log: Path
    ) -> list[str]:
        cmd = [
            self.nsjail,
            "--mode",
            "o",
            "--log",
            str(log),
            "--hostname",
            "testforge",
            "--cwd",
            "/box",
            "--user",
            "65534",
            "--group",
            "65534",
            "--max_cpus",
            "1",
            "--time_limit",
            str(max(1, math.ceil(limits.wall_ms / 1000))),
            "--rlimit_cpu",
            str(max(1, math.ceil(limits.cpu_ms / 1000) + 1)),
            "--rlimit_as",
            str(limits.address_mb) if limits.address_mb else "inf",
            "--rlimit_fsize",
            str(max(1, math.ceil(limits.output_bytes / (1 << 20)))),
            "--rlimit_nofile",
            str(limits.open_files),
            "--rlimit_nproc",
            str(limits.processes),
            "--rlimit_stack",
            str(limits.stack_mb),
            "--rlimit_core",
            "0",
            "--seccomp_string",
            POLICY,
            "--mount",
            f"none:/tmp:tmpfs:size={limits.tmp_mb << 20}",
        ]
        # No /proc: Docker overmounts parts of the container's /proc, and the kernel then
        # refuses a fresh procfs mount inside a user namespace. Test runners do not need it.
        cmd.append("--disable_proc")
        for path in self.read_only:
            cmd += ["--bindmount_ro", path]
        for m in mounts:
            cmd += ["--bindmount" if m.writable else "--bindmount_ro", f"{m.source}:{m.target}"]
        for env in (*BASE_ENV, *limits.env):
            cmd += ["--env", env]
        return [*cmd, "--", *argv]

    def run(
        self,
        argv: list[str],
        *,
        limits: RunLimits,
        mounts: list[Mount],
        stdout: Path,
        stderr: Path,
        log: Path,
        on_start: Callable[[int], None] | None = None,
    ) -> RunResult:
        cmd = self.command(argv, limits, mounts, log)
        # The run, not the service, is what the kernel kills first under memory pressure:
        # raise oom_score_adj (allowed without privileges) and exec nsjail.
        wrapped = ["/bin/sh", "-c", 'echo 1000 > /proc/self/oom_score_adj; exec "$@"', "sh", *cmd]
        started = time.monotonic()
        with (
            open(os.devnull, "rb") as fin,
            stdout.open("wb") as fout,
            stderr.open("wb") as ferr,
        ):
            proc = subprocess.Popen(  # noqa: S603 fixed argv, no shell interpolation of user data
                wrapped, stdin=fin, stdout=fout, stderr=ferr, start_new_session=True, close_fds=True
            )
        if on_start is not None:
            on_start(proc.pid)
        # nsjail enforces the wall limit itself; this is the backstop if nsjail hangs.
        backstop = threading.Timer(limits.wall_ms / 1000 + 5, kill_group, (proc.pid,))
        backstop.start()
        try:
            _, status, usage = os.wait4(proc.pid, 0)
        finally:
            backstop.cancel()
            proc.returncode = 0  # reaped by wait4 above; stop Popen from waiting again
        wall_ms = round((time.monotonic() - started) * 1000)
        cpu_ms = round((usage.ru_utime + usage.ru_stime) * 1000)
        exit_code, sig = _decode(status)
        log_text = log.read_text(errors="replace")[-4000:] if log.exists() else ""
        launch_failed = exit_code == 255 and "Couldn't launch the child process" in log_text
        # nsjail reports a child killed by a signal as 128 + signal; recover the signal.
        if (
            not launch_failed
            and exit_code is not None
            and 128 < exit_code <= 128 + 64
            and "signal" in log_text
        ):
            sig, exit_code = exit_code - 128, None
        return RunResult(
            exit_code=exit_code,
            signal=sig,
            cpu_ms=cpu_ms,
            wall_ms=wall_ms,
            memory_kb=usage.ru_maxrss,
            output_bytes=stdout.stat().st_size + stderr.stat().st_size,
            wall_timed_out=("run time >= time limit" in log_text)
            or wall_ms > limits.wall_ms + 4000,
            launch_failed=launch_failed,
            log=log_text,
        )


def _decode(status: int) -> tuple[int | None, int | None]:
    if os.WIFSIGNALED(status):
        return None, os.WTERMSIG(status)
    return os.WEXITSTATUS(status), None


def kill_group(pid: int) -> None:
    with contextlib.suppress(ProcessLookupError):
        os.killpg(pid, signal.SIGKILL)
