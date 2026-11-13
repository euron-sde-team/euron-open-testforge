"""The sandbox's logic that needs no nsjail: signing, limit classification, the runner
registry, building a workspace, and reading a run's outputs without following links."""

from __future__ import annotations

import base64
import os
import signal
from pathlib import Path

import pytest

from testforge.sandbox.classify import Budget, Measured, classify
from testforge.sandbox.jail import RunLimits, Sandbox
from testforge.sandbox.protocol import RunRequest, SandboxLimits, WorkspaceFile, sign, verify
from testforge.sandbox.runners import framework_for, registry
from testforge.sandbox.server import (
    WorkspaceError,
    prepare,
    read_output,
    vitest_config,
    write_workspace,
)

BUDGET = Budget(
    cpu_ms=10_000,
    wall_ms=20_000,
    memory_mb=512,
    output_bytes=1_000_000,
    memory_overhead_mb=128,
    rss_mode=False,
)


def m(**kw: object) -> Measured:
    base: dict[str, object] = {
        "exit_code": 1,
        "signal": None,
        "cpu_ms": 100,
        "wall_ms": 200,
        "memory_kb": 50_000,
        "stdout_bytes": 10,
        "stderr_bytes": 10,
        "wall_timed_out": False,
        "text": b"",
    }
    base.update(kw)
    return Measured(**base)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("measured", "limit"),
    [
        (m(), None),
        (m(exit_code=0), None),
        (m(stdout_bytes=1_000_000), "output"),
        (m(text=b"OSError: [Errno 27] File too large"), "output"),
        (m(signal=signal.SIGXFSZ), "output"),
        (m(wall_timed_out=True, signal=signal.SIGKILL), "wall_clock"),
        (m(cpu_ms=12_000, signal=signal.SIGKILL), "cpu"),
        (m(signal=signal.SIGXCPU), "cpu"),
        (m(text=b"E   MemoryError"), "memory"),
        (m(text=b"FATAL ERROR: Reached heap limit ... JavaScript heap out of memory"), "memory"),
        (m(signal=signal.SIGKILL, memory_kb=500 * 1024), "memory"),
        (m(text=b"RuntimeError: can't start new thread"), "processes"),
    ],
)
def test_limit_classification(measured: Measured, limit: str | None) -> None:
    found, detail = classify(measured, BUDGET)
    assert found == limit
    assert bool(detail) == (limit is not None)


def test_rss_mode_checks_peak_resident_memory() -> None:
    rss = Budget(10_000, 20_000, 256, 1_000_000, 256, True)
    assert classify(m(memory_kb=600 * 1024), rss)[0] == "memory"
    assert classify(m(memory_kb=400 * 1024), rss)[0] is None


def test_request_signing() -> None:
    body = b'{"x":1}'
    header = sign("s3cret", body, now=1000)
    assert verify("s3cret", body, header, now=1000)
    assert not verify("s3cret", body + b" ", header, now=1000)
    assert not verify("other", body, header, now=1000)
    assert not verify("s3cret", body, header, now=1000 + 301)
    assert not verify("s3cret", body, None)
    assert not verify("s3cret", body, "t=abc,v1=00")


@pytest.mark.parametrize("path", ["../x", "/etc/x", "a//b", "a/../b", "a\\b", "a\x00b"])
def test_workspace_paths_must_stay_inside(path: str) -> None:
    with pytest.raises(ValueError):
        WorkspaceFile(path=path, content_b64="")


def _req(
    files: dict[str, bytes], runner: str = "pytest", targets: list[str] | None = None
) -> RunRequest:
    return RunRequest(
        job_id="job-12345678",
        runner=runner,  # type: ignore[arg-type]
        files=[
            WorkspaceFile(path=p, content_b64=base64.b64encode(c).decode())
            for p, c in files.items()
        ],
        targets=targets or [],
        limits=SandboxLimits(),
    )


def test_workspace_is_written_and_reserved_names_are_refused(tmp_path: Path) -> None:
    box = tmp_path / "box"
    box.mkdir()
    assert write_workspace(box, _req({"a/b.py": b"x = 1\n"})) == 6
    assert (box / "a" / "b.py").read_text() == "x = 1\n"
    for reserved in (".testforge/report.json", "node_modules/vitest/index.js"):
        with pytest.raises(WorkspaceError, match="reserved"):
            write_workspace(box, _req({reserved: b"{}"}))
    bad = _req({"x.py": b""})
    bad.files[0].content_b64 = "!!!"
    with pytest.raises(WorkspaceError, match="base64"):
        write_workspace(box, bad)
    with pytest.raises(WorkspaceError, match="collides"):
        write_workspace(box, _req({"a": b"x"}))


def test_prepare_writes_runner_config(tmp_path: Path) -> None:
    py = tmp_path / "py"
    py.mkdir()
    assert prepare(py, _req({}, targets=["tests"]), registry()["pytest"], "/opt/toolchain") == [
        "tests"
    ]
    assert "norecursedirs" in (py / ".testforge" / "pytest.ini").read_text()
    toolchain = tmp_path / "toolchain"
    (toolchain / "js" / "node_modules" / "vitest").mkdir(parents=True)
    (toolchain / "js" / "node_modules" / ".cache").mkdir()
    js = tmp_path / "js"
    js.mkdir()
    assert prepare(js, _req({}, runner="vitest"), registry()["vitest"], str(toolchain)) == []
    assert os.readlink(js / "node_modules" / "vitest") == f"{toolchain}/js/node_modules/vitest"
    assert not (js / "node_modules" / ".cache").exists()
    config = vitest_config(
        _req({}, runner="vitest", targets=["testforge/a.test.ts"]), "/opt/toolchain"
    )
    assert '"testforge/a.test.ts"' in config and '"provider": "istanbul"' in config


def test_outputs_are_read_without_following_links(tmp_path: Path) -> None:
    box = tmp_path / "box"
    (box / ".testforge" / "coverage").mkdir(parents=True)
    (box / ".testforge" / "report.json").write_text('{"ok": true}')
    (box / ".testforge" / "coverage" / "coverage-final.json").write_text("{}")
    secret = tmp_path / "service-only.txt"
    secret.write_text("SANDBOX_SECRET=do-not-leak")
    os.symlink(secret, box / ".testforge" / "events.jsonl")
    assert read_output(box, "report.json", 1000) == '{"ok": true}'
    assert read_output(box, "coverage/coverage-final.json", 1000) == "{}"
    assert read_output(box, "events.jsonl", 1000) is None
    assert read_output(box, "missing.json", 1000) is None
    assert read_output(box, "report.json", 3) is None  # over the cap
    # A linked directory on the way is refused too.
    os.rename(box / ".testforge" / "coverage", tmp_path / "elsewhere")
    os.symlink(tmp_path / "elsewhere", box / ".testforge" / "coverage")
    assert read_output(box, "coverage/coverage-final.json", 1000) is None


def test_runner_registry_and_commands() -> None:
    runners = registry()
    assert set(runners) == {"pytest", "vitest"}
    assert framework_for("typescript") == "vitest" and framework_for("python") == "pytest"
    with pytest.raises(ValueError):
        framework_for("cobol")
    py = runners["pytest"]
    assert py.memory_mode == "address"
    assert (
        "--cov=/box" in py.command(coverage=True, targets=["t"])
        and py.command(coverage=False, targets=[])[-1] != "--cov=/box"
    )
    assert (
        "NODE_OPTIONS=--max-old-space-size=300 --require /opt/toolchain/js/no-proc.cjs"
        in runners["vitest"].environment(mem_mb=300)
    )


def test_jail_command_isolates_the_run() -> None:
    sb = Sandbox(nsjail="/usr/local/bin/nsjail", read_only=("/usr", "/lib"))
    limits = RunLimits(
        cpu_ms=2500,
        wall_ms=10_000,
        address_mb=512,
        output_bytes=3 << 20,
        processes=64,
        env=("A=1",),
    )
    cmd = sb.command(["python", "-m", "pytest"], limits, [], Path("/tmp/log"))
    joined = " ".join(cmd)
    assert "--disable_proc" in cmd
    assert "--user 65534" in joined and "--group 65534" in joined
    assert "--rlimit_cpu 4" in joined and "--time_limit 10" in joined
    assert "--rlimit_as 512" in joined and "--rlimit_fsize 3" in joined
    assert "--rlimit_nproc 64" in joined and "--rlimit_core 0" in joined
    assert "unshare, setns, mount" in joined and "ptrace" in joined and "bpf" in joined
    assert "--env A=1" in joined and "--env PATH=/usr/bin:/bin" in joined
    # No network option exists: every run gets a fresh, empty network namespace.
    assert "--disable_clone_newnet" not in cmd and "--iface_own" not in joined
    assert cmd[-4:] == ["--", "python", "-m", "pytest"]
