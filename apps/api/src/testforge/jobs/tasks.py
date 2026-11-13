"""Periodic work, run by the scheduler (safe with several replicas: every task claims its
rows or is idempotent)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from testforge.core.container import Container
from testforge.core.tasks import periodic
from testforge.jobs import queue
from testforge.jobs.handlers import mark_failed
from testforge.jobs.models import Job
from testforge.observability import metrics
from testforge.reports.models import Report
from testforge.runs.models import TestRun
from testforge.webhooks import service as webhooks

log = logging.getLogger("testforge.tasks")


@periodic("reap_leases")
async def reap_leases(container: Container) -> int:
    failed = await queue.reap(container, container.settings.max_attempts)
    for job in failed:
        await mark_failed(
            container,
            job,
            f"The worker handling this stopped {job.attempts} times. Try again, and tell an "
            "admin if it keeps happening",
        )
    return len(failed)


@periodic("queue_gauges")
async def queue_gauges(container: Container) -> int:
    async with container.db.sessionmaker() as session:
        depth = await queue.depth(session)
    for status, n in depth.items():
        metrics.QUEUE_DEPTH.labels(status).set(n)
    # One line per tick: CloudWatch turns `queued` into the backlog metric (observability).
    log.info("job queue", extra=depth)
    return 0


@periodic("webhook_deliveries")
async def webhook_deliveries(container: Container) -> int:
    return await webhooks.deliver_due(container)


@periodic("retention")
async def retention(container: Container) -> int:
    """Runs (with their cases and coverage), finished jobs and exported reports older than
    RETENTION_DAYS. The audit log is append-only and never purged here."""
    cutoff = datetime.now(UTC) - timedelta(days=container.settings.retention_days)
    async with container.db.sessionmaker() as session:
        old_reports = (
            await session.execute(
                select(Report.id, Report.object_key).where(Report.created_at < cutoff).limit(500)
            )
        ).all()
        for _, key in old_reports:
            try:
                await container.storage.delete(key)
            except Exception:
                log.warning("report delete failed", exc_info=True)
        if old_reports:
            await session.execute(delete(Report).where(Report.id.in_([r[0] for r in old_reports])))
        gone_runs = await session.execute(delete(TestRun).where(TestRun.created_at < cutoff))
        gone_jobs = await session.execute(
            delete(Job).where(Job.status.in_(("done", "failed")), Job.created_at < cutoff)
        )
        await session.commit()
    return len(old_reports) + int(gone_runs.rowcount or 0) + int(gone_jobs.rowcount or 0)  # type: ignore[attr-defined]
