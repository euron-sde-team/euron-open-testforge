"""Test runs: queue one, execute it in the sandbox, record what happened.

A run's workspace is the import's snapshot plus the chosen generated tests, sent to the
sandbox service (``sandbox/``), which runs pytest or Vitest with no network, no credential
and the run's CPU, memory, output and wall clock budget. The worker records every test
case, explains each failure from the values the same execution captured (``bugs``), reads
the coverage tool's report (``coverage``), and writes one audit entry naming what ran,
from which snapshot, with what result, for whom (A10).
"""

from __future__ import annotations

import base64
import json
import logging
import time
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from testforge.audit.service import Actor, audit
from testforge.bugs.explain import explain
from testforge.core.container import Container
from testforge.core.errors import AppError, NotFoundError
from testforge.coverage import service as coverage
from testforge.generation.models import GeneratedTest
from testforge.jobs import queue
from testforge.observability import metrics
from testforge.projects.access import Principal
from testforge.projects.models import Project
from testforge.runs.models import FINAL_RUN_STATUSES, TestCaseResult, TestRun
from testforge.sandbox.client import SandboxClient
from testforge.sandbox.protocol import RunRequest, RunResult, SandboxLimits, WorkspaceFile
from testforge.sandbox.runners import framework_for
from testforge.sources import service as sources
from testforge.sources.models import SourceImport
from testforge.usage import service as usage
from testforge.webhooks import service as webhooks

log = logging.getLogger("testforge.runs")
JS_LANGUAGES = ("typescript", "javascript")


def _language(imp: SourceImport, wanted: str | None) -> str:
    langs = imp.languages or []
    if wanted:
        if wanted in JS_LANGUAGES and any(lang in JS_LANGUAGES for lang in langs):
            return "typescript" if "typescript" in langs else "javascript"
        if wanted in langs:
            return wanted
        raise AppError(f"This import has no {wanted} code", code="language_not_in_import")
    if "python" in langs:
        return "python"
    for lang in JS_LANGUAGES:
        if lang in langs:
            return lang
    raise AppError("This import has no Python, JavaScript or TypeScript code", code="no_language")


async def create(
    container: Container,
    session: AsyncSession,
    p: Principal,
    *,
    kind: str,
    test_ids: list[uuid.UUID] | None = None,
    import_id: uuid.UUID | None = None,
    language: str | None = None,
    trigger: str = "manual",
    actor: Actor | None = None,
) -> TestRun:
    imp = (
        await sources.get_import(session, p.project_id, import_id)
        if import_id
        else await sources.current_import(session, p.project)
    )
    if imp.status != "ready":
        raise AppError("The import is not analyzed yet", code="import_not_ready")
    tests: Sequence[GeneratedTest] = []
    if kind in ("generated", "all"):
        stmt = select(GeneratedTest).where(GeneratedTest.project_id == p.project_id)
        if test_ids:
            stmt = stmt.where(GeneratedTest.id.in_(test_ids))
        else:
            stmt = stmt.where(GeneratedTest.status == "accepted")
        tests = (await session.scalars(stmt)).all()
        if test_ids and len(tests) != len(set(test_ids)):
            raise NotFoundError("A test in this run does not exist in this project")
        if not language and tests:
            language = tests[0].language
    lang = _language(imp, language)
    family = JS_LANGUAGES if lang in JS_LANGUAGES else (lang,)
    tests = [t for t in tests if t.language in family]
    if kind == "generated" and not tests:
        raise AppError(
            "No generated tests to run: accept some first, or choose them by id",
            code="no_tests",
        )
    project = p.project
    cpu, wall, mem, out = container.settings.clamp_limits(
        project.run_cpu_s, project.run_wall_s, project.run_memory_mb, project.run_output_bytes
    )
    run = TestRun(
        project_id=p.project_id,
        import_id=imp.id,
        kind=kind,
        language=lang,
        framework=framework_for(lang),
        test_ids=[str(t.id) for t in tests],
        limits={"cpu_s": cpu, "wall_s": wall, "memory_mb": mem, "output_bytes": out},
        trigger=trigger,
        triggered_by=p.user_id,
        actor=(actor or p.actor).email or "",
        created_at=datetime.now(UTC),
    )
    session.add(run)
    await session.flush()
    queue.enqueue(session, "run", p.project_id, run.id)
    audit(
        session,
        actor or p.actor,
        "run.requested",
        "test_run",
        run.id,
        kind=kind,
        language=lang,
        tests=run.test_ids[:200],
        import_id=str(imp.id),
        commit=imp.commit_sha,
        trigger=trigger,
        **p.audit_scope(),
    )
    await session.commit()
    await queue.notify(container)
    return run


def _workspace(files: dict[str, str], tests: Sequence[GeneratedTest]) -> list[WorkspaceFile]:
    out = dict(files)
    for t in tests:
        out[t.file_path] = t.code
    return [
        WorkspaceFile(path=p, content_b64=base64.b64encode(text.encode()).decode())
        for p, text in sorted(out.items())
    ]


def _cases(result: RunResult) -> list[dict[str, Any]]:
    """Every test case the run reported. When the run was stopped before the runner wrote
    its report, the event log still has the finished ones and the one that was running."""
    if result.report:
        try:
            report = json.loads(result.report)
            cases: list[dict[str, Any]] = list(report.get("tests", []))
            for err in report.get("collect_errors", []):
                cases.append(
                    {
                        "nodeid": err.get("nodeid") or "collection",
                        "file": (err.get("nodeid") or "").split("::")[0],
                        "name": f"collecting {err.get('nodeid') or 'tests'}",
                        "outcome": "error",
                        "duration_ms": 0,
                        "failure": {
                            "message": err.get("text", "")[:2000],
                            "text": err.get("text", ""),
                        },
                    }
                )
            return cases
        except ValueError:
            pass
    finished: dict[str, dict[str, Any]] = {}
    started: list[str] = []
    for line in result.events.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("event") == "start":
            started.append(ev["nodeid"])
        elif ev.get("event") == "result":
            finished[ev["nodeid"]] = {k: v for k, v in ev.items() if k not in ("event", "t")}
    cases = list(finished.values())
    for nodeid in started:
        if nodeid not in finished:
            cases.append(
                {
                    "nodeid": nodeid,
                    "file": nodeid.split("::")[0],
                    "name": nodeid.split("::")[-1],
                    "outcome": "error",
                    "duration_ms": 0,
                    "failure": {
                        "message": result.limit_detail or "The run stopped while this test ran",
                        "limit": result.limit_exceeded,
                    },
                }
            )
    return cases


def _source_line(code: str | None, line: int | None) -> str | None:
    if not code or not line:
        return None
    lines = code.splitlines()
    return lines[line - 1] if 0 < line <= len(lines) else None


async def execute(container: Container, session: AsyncSession, run: TestRun) -> RunResult:
    """Send the run to the sandbox (the worker's run job). Raises SandboxError for a
    sandbox that could not take it; the caller decides whether to retry."""
    imp = await session.get(SourceImport, run.import_id)
    assert imp is not None
    tests = (
        (
            await session.scalars(
                select(GeneratedTest).where(
                    GeneratedTest.id.in_([uuid.UUID(t) for t in run.test_ids])
                )
            )
        ).all()
        if run.test_ids
        else []
    )
    files = await sources.snapshot_files(container, imp)
    size = sum(len(t.encode()) for t in files.values()) + sum(len(t.code.encode()) for t in tests)
    if size > container.settings.max_workspace_bytes:
        raise AppError(
            f"The workspace is {size} bytes, over the {container.settings.max_workspace_bytes} "
            "bytes a run may send to the sandbox (MAX_WORKSPACE_BYTES)",
            code="workspace_too_large",
        )
    # Only the generated tests run for kind "generated": the project's own suite stays out.
    targets = sorted({t.file_path for t in tests}) if run.kind == "generated" else []
    run.status = "running"
    run.started_at = datetime.now(UTC)
    await session.commit()
    lim = run.limits
    req = RunRequest(
        job_id=run.id.hex,
        runner=run.framework,
        files=_workspace(files, tests),
        targets=targets,
        coverage=True,
        limits=SandboxLimits(
            cpu_s=lim["cpu_s"],
            wall_s=lim["wall_s"],
            memory_mb=lim["memory_mb"],
            output_bytes=lim["output_bytes"],
        ),
    )
    client = SandboxClient(
        container.http, container.settings.sandbox_url, container.settings.sandbox_secret
    )
    started = time.monotonic()
    try:
        return await client.run(req)
    finally:
        metrics.SANDBOX_SECONDS.observe(time.monotonic() - started)


async def record(
    container: Container, session: AsyncSession, run: TestRun, result: RunResult
) -> None:
    """Store a finished run: cases, failures explained, coverage, totals, audit, usage."""
    tests = (
        (
            await session.scalars(
                select(GeneratedTest).where(
                    GeneratedTest.id.in_([uuid.UUID(t) for t in run.test_ids])
                )
            )
        ).all()
        if run.test_ids
        else []
    )
    by_file = {t.file_path: t for t in tests}
    imp = await session.get(SourceImport, run.import_id)
    project = await session.get(Project, run.project_id)
    assert imp is not None and project is not None
    files: dict[str, str] | None = None
    counts = {"passed": 0, "failed": 0, "error": 0, "skipped": 0}
    latest: dict[uuid.UUID, str] = {}
    for case in _cases(result):
        outcome = case.get("outcome", "error")
        outcome = outcome if outcome in counts else "error"
        counts[outcome] += 1
        test = by_file.get(case.get("file") or "")
        failure = None
        if outcome in ("failed", "error") and case.get("failure"):
            code = test.code if test else None
            if code is None and case.get("file"):
                if files is None:
                    files = await sources.snapshot_files(container, imp)
                code = files.get(case["file"])
            failure = explain(case, _source_line(code, (case.get("failure") or {}).get("line")))
            if case["failure"].get("limit"):
                failure["kind"] = "limit"
                failure["limit"] = case["failure"]["limit"]
        session.add(
            TestCaseResult(
                run_id=run.id,
                generated_test_id=test.id if test else None,
                nodeid=str(case.get("nodeid", ""))[:600],
                file=str(case.get("file") or "")[:500],
                name=str(case.get("name") or "")[:300],
                outcome=outcome,
                duration_ms=float(case.get("duration_ms") or 0),
                message=str((case.get("failure") or {}).get("message") or "")[:4000],
                failure=failure,
            )
        )
        if test is not None:
            worst = latest.get(test.id)
            if worst is None or outcome in ("failed", "error"):
                latest[test.id] = outcome
    for test_id, outcome in latest.items():
        await session.execute(
            update(GeneratedTest)
            .where(GeneratedTest.id == test_id)
            .values(last_outcome=outcome, last_run_id=run.id)
        )
    run.passed, run.failed, run.errors, run.skipped = (
        counts["passed"],
        counts["failed"],
        counts["error"],
        counts["skipped"],
    )
    run.exit_code, run.signal = result.exit_code, result.signal
    run.cpu_ms, run.wall_ms = result.cpu_ms, result.wall_ms
    run.memory_kb, run.output_bytes = result.memory_kb, result.output_bytes
    run.stdout_tail, run.stderr_tail = result.stdout_tail[-8000:], result.stderr_tail[-8000:]
    run.limit_exceeded = result.limit_exceeded
    if result.error:
        run.status, run.message = "error", result.error
    elif result.limit_exceeded:
        run.status, run.message = "limit_exceeded", result.limit_detail
        metrics.LIMITS_CROSSED.labels(result.limit_exceeded).inc()
    elif run.failed or run.errors:
        run.status = "failed"
    elif run.passed:
        run.status = "passed"
    else:
        run.status = "error"
        run.message = (
            "The run finished without running any test. "
            + (result.stderr_tail or result.stdout_tail)[-500:]
        )
    if result.coverage and result.coverage_tool:
        cov = await coverage.store(session, run, imp, result.coverage_tool, result.coverage)
        run.coverage_percent = cov.line_percent if cov else None
    run.finished_at = datetime.now(UTC)
    metrics.RUNS.labels(run.status).inc()
    await usage.record(
        session,
        run.project_id,
        runs=1,
        runs_failed=1 if run.status != "passed" else 0,
        sandbox_ms=result.wall_ms,
    )
    audit(
        session,
        Actor(run.triggered_by, run.actor or "worker", "system"),
        "run.finished",
        "test_run",
        run.id,
        status=run.status,
        kind=run.kind,
        passed=run.passed,
        failed=run.failed,
        errors=run.errors,
        limit=run.limit_exceeded,
        coverage=run.coverage_percent,
        tests=run.test_ids[:200],
        import_id=str(imp.id),
        source=imp.label,
        commit=imp.commit_sha,
        triggered_by=run.actor,
        trigger=run.trigger,
        project_id=run.project_id,
        org_id=project.org_id,
    )
    await webhooks.emit(
        session, run.project_id, "run.finished", run_payload(container, run, project)
    )
    await session.commit()


def run_payload(container: Container, run: TestRun, project: Project) -> dict[str, Any]:
    return {
        "event": "run.finished",
        "project": {"id": str(project.id), "name": project.name},
        "run": {
            "id": str(run.id),
            "status": run.status,
            "kind": run.kind,
            "passed": run.passed,
            "failed": run.failed,
            "errors": run.errors,
            "limit_exceeded": run.limit_exceeded,
            "coverage_percent": run.coverage_percent,
            "url": (
                f"{container.settings.public_url.rstrip('/')}/projects/{project.id}/runs/{run.id}"
            ),
        },
    }


async def fail(session: AsyncSession, run: TestRun, message: str) -> None:
    run.status = "error"
    run.message = message[:2000]
    run.finished_at = datetime.now(UTC)
    metrics.RUNS.labels("error").inc()
    await session.commit()


# ── Reading ──────────────────────────────────────────────────────────────────────────


async def get(session: AsyncSession, project_id: uuid.UUID, run_id: uuid.UUID) -> TestRun:
    run = await session.scalar(
        select(TestRun).where(TestRun.id == run_id, TestRun.project_id == project_id)
    )
    if run is None:
        raise NotFoundError("Run not found")
    return run


async def list_runs(
    session: AsyncSession,
    project_id: uuid.UUID,
    *,
    status: str | None = None,
    limit: int = 50,
    before: datetime | None = None,
) -> Sequence[TestRun]:
    stmt = select(TestRun).where(TestRun.project_id == project_id)
    if status:
        stmt = stmt.where(TestRun.status == status)
    if before:
        stmt = stmt.where(TestRun.created_at < before)
    return (await session.scalars(stmt.order_by(TestRun.created_at.desc()).limit(limit))).all()


async def cases(session: AsyncSession, run_id: uuid.UUID) -> Sequence[TestCaseResult]:
    order = {"failed": 0, "error": 1, "passed": 2, "skipped": 3}
    rows = (
        await session.scalars(select(TestCaseResult).where(TestCaseResult.run_id == run_id))
    ).all()
    return sorted(rows, key=lambda c: (order.get(c.outcome, 9), c.nodeid))


def is_final(run: TestRun) -> bool:
    return run.status in FINAL_RUN_STATUSES
