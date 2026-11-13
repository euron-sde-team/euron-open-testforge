"""What the worker does with each kind of job, and how a failed job marks its record."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from testforge.core.container import Container
from testforge.core.errors import AppError
from testforge.generation import service as generation
from testforge.generation.models import Generation
from testforge.jobs.models import Job
from testforge.pulls import service as pulls
from testforge.runs import service as runs
from testforge.runs.models import TestRun
from testforge.sources import service as sources
from testforge.sources.models import SourceImport

log = logging.getLogger("testforge.jobs")


class RetryLaterError(Exception):
    """Put the job back without counting the attempt (the sandbox is busy, say)."""

    def __init__(self, delay_s: float, reason: str, *, count: bool = False) -> None:
        super().__init__(reason)
        self.delay_s = delay_s
        self.reason = reason
        self.count = count


async def handle(container: Container, session: AsyncSession, job: Job) -> None:
    if job.kind == "import":
        imp = await session.get(SourceImport, job.ref_id)
        if imp is None:
            return
        await sources.process(container, session, imp)
        if imp.kind == "pull_request":
            await pulls.scope_after_import(session, imp)
            await session.commit()
    elif job.kind == "generate":
        gen = await session.get(Generation, job.ref_id)
        if gen is None or gen.status in ("done", "failed"):
            return
        await generation.run(container, session, gen)
    elif job.kind == "run":
        await _run(container, session, job)


async def _run(container: Container, session: AsyncSession, job: Job) -> None:
    from testforge.observability import metrics
    from testforge.sandbox.client import SandboxError

    run = await session.get(TestRun, job.ref_id)
    if run is None or runs.is_final(run):
        return
    try:
        result = await runs.execute(container, session, run)
    except AppError as exc:
        await runs.fail(session, run, exc.message)
        return
    except SandboxError as exc:
        metrics.SANDBOX_FAILURES.labels(exc.reason).inc()
        # One line per failure: CloudWatch counts these (the SandboxFailures alarm).
        log.warning("sandbox failure", extra={"reason": exc.reason, "run": str(run.id)})
        if exc.retryable:
            run.status = "queued"
            await session.commit()
            raise RetryLaterError(
                5 if exc.reason == "busy" else 15, exc.message, count=exc.reason != "busy"
            ) from exc
        await runs.fail(session, run, exc.message)
        return
    if result.error:
        metrics.SANDBOX_FAILURES.labels("launch").inc()
        log.warning("sandbox failure", extra={"reason": "launch", "run": str(run.id)})
    await runs.record(container, session, run, result)


async def mark_failed(container: Container, job: Job, message: str) -> None:
    """A job that will not be tried again: its record says why, in words."""
    async with container.db.sessionmaker() as session:
        if job.kind == "import":
            imp = await session.get(SourceImport, job.ref_id)
            if imp is not None and imp.status not in ("ready", "failed"):
                imp.status, imp.error = "failed", message
                if imp.kind == "pull_request":
                    await pulls.scope_after_import(session, imp)
        elif job.kind == "generate":
            gen = await session.get(Generation, job.ref_id)
            if gen is not None and gen.status not in ("done", "failed"):
                gen.status, gen.error_code, gen.error = "failed", "worker_failed", message
        elif job.kind == "run":
            run = await session.get(TestRun, job.ref_id)
            if run is not None and not runs.is_final(run):
                await runs.fail(session, run, message)
        await session.commit()
