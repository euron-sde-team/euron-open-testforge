"""Coverage reports: stored per run from the coverage tool's own report, projected onto the
import's code units (the untested-code detector reads them), and a trend per project."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testforge.coverage.models import CoverageReport
from testforge.coverage.parse import Coverage, CoverageError, parse, unit_percent
from testforge.runs.models import TestRun
from testforge.sources.models import CodeUnit, SourceImport

log = logging.getLogger("testforge.coverage")


async def store(
    session: AsyncSession, run: TestRun, imp: SourceImport, tool: str, text: str
) -> Coverage | None:
    try:
        cov = parse(tool, text)
    except CoverageError as exc:
        log.warning("unreadable coverage report", extra={"run": str(run.id), "error": str(exc)})
        return None
    session.add(
        CoverageReport(
            project_id=run.project_id,
            run_id=run.id,
            import_id=imp.id,
            tool=cov.tool,
            lines_total=cov.lines_total,
            lines_covered=cov.lines_covered,
            line_percent=cov.line_percent,
            branches_total=cov.branches_total,
            branches_covered=cov.branches_covered,
            branch_percent=cov.branch_percent,
            files=[f.as_dict() for f in cov.files][:2000],
        )
    )
    by_path = cov.by_path()
    units = (await session.scalars(select(CodeUnit).where(CodeUnit.import_id == imp.id))).all()
    for u in units:
        fc = by_path.get(u.file)
        if fc is None:
            continue
        body = (u.details or {}).get("statement_lines") or None
        pct = unit_percent(fc, u.start_line, u.end_line, body)
        if pct is not None:
            u.covered_percent = pct
    return cov


async def for_run(session: AsyncSession, run_id: uuid.UUID) -> CoverageReport | None:
    return await session.scalar(select(CoverageReport).where(CoverageReport.run_id == run_id))


async def trend(
    session: AsyncSession, project_id: uuid.UUID, limit: int = 60
) -> Sequence[CoverageReport]:
    rows = (
        await session.scalars(
            select(CoverageReport)
            .where(CoverageReport.project_id == project_id)
            .order_by(CoverageReport.created_at.desc())
            .limit(limit)
        )
    ).all()
    return list(reversed(rows))
