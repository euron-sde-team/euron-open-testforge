"""The sandbox service: the only place TestForge executes code (generated tests, uploaded
projects and their own test suites), for requests signed by the worker.

It holds no database, storage, provider or GitHub credential: only the request-signing
secret (shared with the worker), and that never reaches a run. Each run gets its own
workspace with the files the worker sent, runs pytest or Vitest inside nsjail with no
network and the run's CPU, memory, output and wall clock budget (``jail.py``), and returns
the measurements, the limit crossed if any, and the runner plugin's report and coverage
files. One run at a time per process (``SANDBOX_CONCURRENCY``); runs are killed when they
cross a limit, when the worker disconnects, or on ``DELETE /v1/runs/<job>``.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import contextlib
import json
import logging
import os
import shutil
import stat
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.responses import Response

from testforge.core.config import Settings, get_settings
from testforge.core.logs import configure_logging
from testforge.sandbox.classify import Budget, Measured, classify
from testforge.sandbox.jail import Mount, RunLimits, Sandbox, kill_group
from testforge.sandbox.protocol import SIGNATURE_HEADER, RunRequest, RunResult, verify
from testforge.sandbox.runners import Runner, registry

log = logging.getLogger("testforge.sandbox")

RUNS = Counter("testforge_sandbox_runs_total", "Sandboxed runs", ["runner", "outcome"])
RUN_SECONDS = Histogram(
    "testforge_sandbox_run_seconds",
    "Wall time of one sandboxed run, measured by the sandbox",
    ["runner"],
    buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60, 120, 300, 900),
)

OUT_DIR = ".testforge"
# Names the worker may not send: the sandbox writes them itself.
RESERVED = (OUT_DIR, "node_modules")
TAIL_BYTES = 16_000
REPORT_BYTES = 5_000_000
EVENTS_BYTES = 2_000_000
COVERAGE_BYTES = 30_000_000
MAX_WORKSPACE_BYTES = 60_000_000

PYTEST_INI = """[pytest]
norecursedirs = .testforge node_modules .git .venv venv env __pycache__ dist build site-packages
python_files = test_*.py *_test.py
python_functions = test_*
"""

COVERAGERC = """[run]
omit =
    */tests/*
    */test_*.py
    *_test.py
    */conftest.py
    .testforge/*
    */.testforge/*
[json]
pretty_print = false
"""

JS_TEST_GLOBS = [
    "**/*.{test,spec}.{js,mjs,cjs,ts,mts,cts,jsx,tsx}",
    "**/__tests__/**/*.{js,mjs,cjs,ts,mts,cts,jsx,tsx}",
]
JS_EXCLUDES = ["**/node_modules/**", "**/.testforge/**", "**/dist/**", "**/build/**", "**/.git/**"]


class WorkspaceError(Exception):
    """The request's files cannot become a workspace (a path that leaves it, too large)."""


def _safe(base: Path, rel: str) -> Path:
    path = (base / rel).resolve()
    if not path.is_relative_to(base) or path == base:
        raise WorkspaceError(f"file path {rel!r} leaves the workspace")
    first = Path(rel).parts[0]
    if first in RESERVED:
        raise WorkspaceError(f"file path {rel!r} is reserved for the sandbox")
    return path


def write_workspace(box: Path, req: RunRequest) -> int:
    """Write the request's files under ``box``. Returns the bytes written."""
    total = 0
    for f in req.files:
        target = _safe(box, f.path)
        try:
            data = base64.b64decode(f.content_b64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise WorkspaceError(f"file {f.path!r} is not valid base64") from exc
        total += len(data)
        if total > MAX_WORKSPACE_BYTES:
            raise WorkspaceError("the workspace is larger than the sandbox accepts")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise WorkspaceError(f"file path {f.path!r} collides with a directory")
        target.write_bytes(data)
    return total


def vitest_config(req: RunRequest, toolchain: str) -> str:
    targets = [t for t in req.targets if t]
    config: dict[str, Any] = {
        # The run's own private /tmp inside the jail, not the service's.
        "cacheDir": "/tmp/vite-cache",  # noqa: S108
        "test": {
            "root": "/box",
            "include": targets or JS_TEST_GLOBS,
            "exclude": JS_EXCLUDES,
            "reporters": [f"{toolchain}/js/testforge-reporter.mjs"],
            "includeTaskLocation": True,
            # One child process runs the files in turn: every Node process gets the heap
            # cap and the /proc shim from NODE_OPTIONS (worker threads would not).
            "pool": "forks",
            "poolOptions": {"forks": {"singleFork": True}},
            "watch": False,
            "fileParallelism": False,
            "passWithNoTests": True,
            "coverage": {
                "enabled": False,
                "provider": "istanbul",
                "reporter": ["json"],
                "reportsDirectory": f"/box/{OUT_DIR}/coverage",
                "reportOnFailure": True,
                "all": True,
                "include": ["**/*.{js,mjs,cjs,ts,mts,cts,jsx,tsx}"],
                "exclude": [*JS_EXCLUDES, *JS_TEST_GLOBS, "**/*.config.*", "**/*.d.ts"],
            },
        },
    }
    return "export default " + json.dumps(config, indent=2) + ";\n"


def prepare(box: Path, req: RunRequest, runner: Runner, toolchain: str) -> list[str]:
    """Write the runner's configuration into the workspace and return the targets."""
    out = box / OUT_DIR
    out.mkdir()
    if runner.id == "pytest":
        (out / "pytest.ini").write_text(PYTEST_INI)
        (out / "coveragerc").write_text(COVERAGERC)
        return list(req.targets)
    (out / "vitest.config.mjs").write_text(vitest_config(req, toolchain))
    # Tests import "vitest": resolve every toolchain package through a link in a writable
    # node_modules of the run's own (Vite writes temporary files there).
    modules = box / "node_modules"
    modules.mkdir()
    source = Path(toolchain) / "js" / "node_modules"
    for entry in source.iterdir():
        if entry.name.startswith(".") and entry.name != ".bin":
            continue
        (modules / entry.name).symlink_to(f"{toolchain}/js/node_modules/{entry.name}")
    return []


def read_output(box: Path, rel: str, limit: int) -> str | None:
    """Read a file the run wrote, refusing anything but a regular file reached without
    following a link: a test could replace its report with a symlink to a file only the
    service can read, and the service must never hand that file back."""
    parts = [OUT_DIR, *Path(rel).parts]
    fd = os.open(box, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for name in parts[:-1]:
            nxt = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nxt
        leaf = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    except OSError:
        os.close(fd)
        return None
    os.close(fd)
    try:
        if not stat.S_ISREG(os.fstat(leaf).st_mode):
            return None
        with os.fdopen(leaf, "rb") as fh:
            data = fh.read(limit + 1)
    except OSError:
        return None
    if len(data) > limit:
        return None
    return data.decode("utf-8", "replace")


def _tail(path: Path, limit: int) -> str:
    try:
        size = path.stat().st_size
        with path.open("rb") as fh:
            fh.seek(max(0, size - limit))
            return fh.read().decode("utf-8", "replace")
    except FileNotFoundError:
        return ""


def _remove(path: Path) -> None:
    def retry(fn: Callable[..., Any], p: str, _exc: BaseException) -> None:
        # A run may chmod its own files to 000; the service owns them and can undo that.
        with contextlib.suppress(OSError):
            os.chmod(os.path.dirname(p), 0o700)
            os.chmod(p, 0o700)
            fn(p)

    shutil.rmtree(path, onexc=retry)


class Runs:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.sandbox = Sandbox(nsjail=settings.nsjail_path)
        self.runners = registry()
        self.slots = asyncio.Semaphore(settings.sandbox_concurrency)
        self.pids: dict[str, int] = {}
        self.root = Path(settings.sandbox_work_dir)

    def kill(self, job_id: str) -> bool:
        pid = self.pids.get(job_id)
        if pid is None:
            return False
        kill_group(pid)
        return True

    def execute_sync(self, req: RunRequest, workdir: Path) -> RunResult:
        runner = self.runners[req.runner]
        box = workdir / "box"
        box.mkdir(parents=True)
        try:
            write_workspace(box, req)
            targets = prepare(box, req, runner, self.settings.toolchain_dir)
        except (WorkspaceError, OSError) as exc:
            return RunResult(exit_code=None, error=f"The workspace could not be built: {exc}")
        lim = req.limits
        limits = RunLimits(
            cpu_ms=lim.cpu_s * 1000,
            wall_ms=lim.wall_s * 1000,
            address_mb=lim.memory_mb + runner.memory_overhead_mb
            if runner.memory_mode == "address"
            else None,
            output_bytes=lim.output_bytes,
            processes=runner.processes,
            env=runner.environment(mem_mb=lim.memory_mb),
        )
        # Only "localhost" resolves (Vite looks it up on start); there is no route anywhere.
        hosts = workdir / "hosts"
        hosts.write_text("127.0.0.1 localhost\n::1 localhost\n")
        mounts = [
            Mount(Path(self.settings.toolchain_dir), self.settings.toolchain_dir),
            Mount(hosts, "/etc/hosts"),
            Mount(box, "/box", writable=True),
        ]
        argv = runner.command(coverage=req.coverage, targets=targets)
        out, err, nslog = workdir / "stdout", workdir / "stderr", workdir / "nsjail.log"
        run = self.sandbox.run(
            argv,
            limits=limits,
            mounts=mounts,
            stdout=out,
            stderr=err,
            log=nslog,
            on_start=lambda pid: self.pids.__setitem__(req.job_id, pid),
        )
        if run.launch_failed:
            log.error("nsjail could not start the run: %s", run.log[-500:])
            return RunResult(
                exit_code=None, error="The sandbox could not start the run (nsjail failed)"
            )
        stdout_tail, stderr_tail = _tail(out, TAIL_BYTES), _tail(err, TAIL_BYTES)
        report = read_output(box, "report.json", REPORT_BYTES)
        events = read_output(box, "events.jsonl", EVENTS_BYTES) or ""
        coverage = read_output(box, runner.coverage_file, COVERAGE_BYTES) if req.coverage else None
        failure_text = "\n".join(
            line for line in events.splitlines() if '"failed"' in line or "collect_error" in line
        )
        measured = Measured(
            exit_code=run.exit_code,
            signal=run.signal,
            cpu_ms=run.cpu_ms,
            wall_ms=run.wall_ms,
            memory_kb=run.memory_kb,
            stdout_bytes=out.stat().st_size,
            stderr_bytes=err.stat().st_size,
            wall_timed_out=run.wall_timed_out,
            text=(stderr_tail + stdout_tail + failure_text + run.log[-1000:]).encode(),
        )
        limit, detail = classify(
            measured,
            Budget(
                cpu_ms=limits.cpu_ms,
                wall_ms=limits.wall_ms,
                memory_mb=lim.memory_mb,
                output_bytes=lim.output_bytes,
                memory_overhead_mb=runner.memory_overhead_mb,
                rss_mode=runner.memory_mode == "rss",
            ),
        )
        return RunResult(
            exit_code=run.exit_code,
            signal=run.signal,
            cpu_ms=run.cpu_ms,
            wall_ms=run.wall_ms,
            memory_kb=run.memory_kb,
            output_bytes=run.output_bytes,
            limit_exceeded=limit,
            limit_detail=detail,
            stdout_tail=stdout_tail,
            stderr_tail=stderr_tail,
            report=report,
            events=events,
            coverage=coverage,
            coverage_tool=runner.coverage_tool if coverage else "",
        )

    async def execute(self, req: RunRequest) -> RunResult:
        workdir = self.root / req.job_id
        if workdir.exists():
            raise HTTPException(409, "a run with this id is in progress")
        workdir.mkdir(parents=True)
        try:
            return await asyncio.to_thread(self.execute_sync, req, workdir)
        finally:
            self.pids.pop(req.job_id, None)
            await asyncio.to_thread(_remove, workdir)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    runs = Runs(settings)
    runs.root.mkdir(parents=True, exist_ok=True)
    has_nsjail = os.path.exists(settings.nsjail_path)
    app = FastAPI(
        title="Euron Open TestForge sandbox", docs_url=None, redoc_url=None, openapi_url=None
    )

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        return {"status": "ok", "nsjail": has_nsjail, "runners": sorted(runs.runners)}

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.post("/v1/runs")
    async def execute(request: Request) -> JSONResponse:
        body = await request.body()
        if not verify(settings.sandbox_secret, body, request.headers.get(SIGNATURE_HEADER)):
            return JSONResponse({"error": "unsigned or stale request"}, status_code=401)
        req = RunRequest.model_validate_json(body)
        try:
            await asyncio.wait_for(runs.slots.acquire(), timeout=30)
        except TimeoutError:
            return JSONResponse({"error": "the sandbox is busy"}, status_code=429)
        started = time.monotonic()
        try:
            task = asyncio.create_task(runs.execute(req))

            async def watch() -> None:
                # The worker hung up (its job was cancelled or lost its lease): kill the run.
                while not task.done():
                    if await request.is_disconnected():
                        runs.kill(req.job_id)
                        return
                    await asyncio.sleep(0.5)

            watcher = asyncio.create_task(watch())
            try:
                result = await task
            finally:
                watcher.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await watcher
        finally:
            runs.slots.release()
        outcome = "error" if result.error else result.limit_exceeded or "completed"
        RUNS.labels(req.runner, outcome).inc()
        RUN_SECONDS.labels(req.runner).observe(time.monotonic() - started)
        log.info(
            "run done",
            extra={
                "runner": req.runner,
                "exit": result.exit_code,
                "limit": result.limit_exceeded,
                "ms": result.wall_ms,
            },
        )
        return JSONResponse(result.model_dump())

    @app.delete("/v1/runs/{job_id}")
    async def kill(job_id: str, request: Request) -> dict[str, bool]:
        if not verify(settings.sandbox_secret, b"", request.headers.get(SIGNATURE_HEADER)):
            raise HTTPException(401, "unsigned or stale request")
        return {"killed": runs.kill(job_id)}

    return app
