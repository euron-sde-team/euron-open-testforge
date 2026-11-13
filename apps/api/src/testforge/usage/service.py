"""Usage counters (atomic upserts) and the report built from the daily rollups."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from testforge.usage.models import UsageDaily
from testforge.usage.schemas import UsageByDay, UsageByModel, UsageCounts, UsageReport

COUNTERS = (
    "generations",
    "tests_accepted",
    "tests_rejected",
    "runs",
    "runs_failed",
    "sandbox_ms",
    "input_tokens",
    "output_tokens",
)


async def record(
    session: AsyncSession,
    project_id: uuid.UUID,
    model: str = "",
    *,
    day: date | None = None,
    **counts: int,
) -> None:
    """Add ``counts`` to today's row (the caller commits). Concurrent writers add, never
    overwrite: the update is ``column = column + excluded.column``."""
    values = {name: int(counts.get(name, 0)) for name in COUNTERS}
    stmt = insert(UsageDaily).values(
        project_id=project_id, day=day or datetime.now(UTC).date(), model=model[:260], **values
    )
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=[UsageDaily.project_id, UsageDaily.day, UsageDaily.model],
            set_={name: getattr(UsageDaily, name) + stmt.excluded[name] for name in COUNTERS},
        )
    )


async def report(session: AsyncSession, project_id: uuid.UUID, days: int) -> UsageReport:
    since = datetime.now(UTC).date() - timedelta(days=days - 1)
    sums = [func.coalesce(func.sum(getattr(UsageDaily, c)), 0).label(c) for c in COUNTERS]
    where = (UsageDaily.project_id == project_id, UsageDaily.day >= since)

    def counts(row: object) -> dict[str, int]:
        return {c: int(getattr(row, c)) for c in COUNTERS}

    total = (await session.execute(select(*sums).where(*where))).one()
    by_day = (
        await session.execute(
            select(UsageDaily.day, *sums)
            .where(*where)
            .group_by(UsageDaily.day)
            .order_by(UsageDaily.day)
        )
    ).all()
    by_model = (
        await session.execute(
            select(UsageDaily.model, *sums)
            .where(*where, UsageDaily.model != "")
            .group_by(UsageDaily.model)
            .order_by(func.sum(UsageDaily.generations).desc())
        )
    ).all()
    return UsageReport(
        days=days,
        totals=UsageCounts(**counts(total)),
        by_day=[UsageByDay(day=r.day, **counts(r)) for r in by_day],
        by_model=[UsageByModel(model=r.model, **counts(r)) for r in by_model],
    )
