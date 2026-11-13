"""The job queue, in PostgreSQL: claim with ``FOR UPDATE SKIP LOCKED``, lease, finish under
the lease, and reap the leases of workers that died.

A worker's final write carries its own name as a compare-and-set on ``lease_owner``; once
the reaper has handed the job to another worker, the old worker's write matches nothing
and is dropped. Wake-ups travel over pub/sub (Redis, or in process): the queue channel
tells idle workers to look again, and each job's own channel tells an API request waiting
for it that it finished.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from testforge.core.container import Container
from testforge.jobs.models import Job

QUEUE_CHANNEL = "tf:queue"


def job_channel(ref_id: uuid.UUID) -> str:
    return f"tf:job:{ref_id}"


def enqueue(session: AsyncSession, kind: str, project_id: uuid.UUID, ref_id: uuid.UUID) -> Job:
    """Add a job in the caller's transaction (the job exists exactly when its record does)."""
    job = Job(kind=kind, project_id=project_id, ref_id=ref_id)
    session.add(job)
    return job


async def notify(container: Container) -> None:
    await container.pubsub.publish(QUEUE_CHANNEL, "1")


async def claim(session: AsyncSession, owner: str, lease_s: float) -> Job | None:
    pick = (
        select(Job.id)
        .where(Job.status == "queued", Job.available_at <= func.now())
        .order_by(Job.available_at)
        .limit(1)
        .with_for_update(skip_locked=True)
        .scalar_subquery()
    )
    job = await session.scalar(
        update(Job)
        .where(Job.id == pick)
        .values(
            status="running",
            lease_owner=owner,
            lease_expires_at=func.now() + timedelta(seconds=lease_s),
            attempts=Job.attempts + 1,
        )
        .returning(Job)
        .execution_options(synchronize_session=False)
    )
    if job is None:
        await session.rollback()
        return None
    await session.commit()
    return job


async def renew(session: AsyncSession, job_id: uuid.UUID, owner: str, lease_s: float) -> bool:
    """Extend a running job's lease (long sandbox runs). False when the lease was lost."""
    result = await session.execute(
        update(Job)
        .where(Job.id == job_id, Job.lease_owner == owner, Job.status == "running")
        .values(lease_expires_at=func.now() + timedelta(seconds=lease_s))
    )
    await session.commit()
    return bool(result.rowcount)  # type: ignore[attr-defined]


async def finish(
    session: AsyncSession, job_id: uuid.UUID, owner: str, status: str, error: str | None = None
) -> bool:
    """Mark the job final under this worker's lease. False when the lease was lost (the
    caller must then commit nothing else)."""
    result = await session.execute(
        update(Job)
        .where(Job.id == job_id, Job.lease_owner == owner, Job.status == "running")
        .values(
            status=status,
            error=error,
            lease_owner=None,
            lease_expires_at=None,
            finished_at=func.now(),
        )
    )
    return bool(result.rowcount)  # type: ignore[attr-defined]


async def retry_later(
    session: AsyncSession, job_id: uuid.UUID, owner: str, delay_s: float, *, count: bool
) -> bool:
    """Put a job back for a transient reason (the sandbox is busy). ``count=False`` gives
    the attempt back, so waiting for capacity never fails a job."""
    values: dict[str, object] = {
        "status": "queued",
        "lease_owner": None,
        "lease_expires_at": None,
        "available_at": func.now() + timedelta(seconds=delay_s),
    }
    if not count:
        values["attempts"] = Job.attempts - 1
    result = await session.execute(
        update(Job)
        .where(Job.id == job_id, Job.lease_owner == owner, Job.status == "running")
        .values(**values)
    )
    await session.commit()
    return bool(result.rowcount)  # type: ignore[attr-defined]


async def reap(container: Container, max_attempts: int, limit: int = 100) -> list[Job]:
    """Jobs whose worker stopped: back to the queue with backoff, or failed after
    ``max_attempts`` claims. Returns the jobs that failed for good (their records are
    marked failed by the caller)."""
    now = datetime.now(UTC)
    failed: list[Job] = []
    async with container.db.sessionmaker() as session:
        rows = (
            await session.scalars(
                select(Job)
                .where(Job.status == "running", Job.lease_expires_at < now)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        ).all()
        for job in rows:
            if job.attempts >= max_attempts:
                job.status = "failed"
                job.error = f"the worker stopped {job.attempts} times while handling this job"
                job.finished_at = now
                failed.append(job)
            else:
                job.status = "queued"
                job.available_at = now + timedelta(seconds=min(2**job.attempts, 30))
            job.lease_owner = None
            job.lease_expires_at = None
        await session.commit()
    if rows:
        await notify(container)
    return failed


async def depth(session: AsyncSession) -> dict[str, int]:
    rows = (
        await session.execute(
            select(Job.status, func.count())
            .where(Job.status.in_(("queued", "running")))
            .group_by(Job.status)
        )
    ).all()
    out = {"queued": 0, "running": 0} | {str(s): int(n) for s, n in rows}
    oldest = await session.scalar(
        select(func.min(Job.available_at)).where(
            Job.status == "queued", Job.available_at <= func.now()
        )
    )
    out["oldest_wait_s"] = int((datetime.now(UTC) - oldest).total_seconds()) if oldest else 0
    return out


async def wait_for(container: Container, ref_id: uuid.UUID, timeout_s: float) -> None:
    """Return when the job for ``ref_id`` is final or ``timeout_s`` passes. Listens on the
    job's channel and also polls, so a lost wake-up only costs a poll interval."""
    deadline = time.monotonic() + timeout_s
    async with container.pubsub.listen(job_channel(ref_id)) as sub:
        while True:
            async with container.db.sessionmaker() as session:
                status = await session.scalar(
                    select(Job.status)
                    .where(Job.ref_id == ref_id)
                    .order_by(Job.created_at.desc())
                    .limit(1)
                )
            if status is None or status in ("done", "failed"):
                return
            left = deadline - time.monotonic()
            if left <= 0:
                return
            with contextlib.suppress(asyncio.TimeoutError):
                await sub.get(min(left, 1.0))
