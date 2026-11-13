"""The project overview: tests, pass/fail, coverage trend, untested code, recent activity
(one request for the dashboard's first screen)."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter
from sqlalchemy import func, select

from testforge.core.deps import SessionDep
from testforge.core.errors import AppError
from testforge.core.schemas import ApiModel
from testforge.coverage import service as coverage
from testforge.generation import service as generation
from testforge.generation.models import Generation
from testforge.projects.access import Viewer
from testforge.runs import service as runs
from testforge.runs.models import TestRun
from testforge.runs.schemas import RunOut
from testforge.sources import service as sources
from testforge.sources.schemas import ImportOut

router = APIRouter(prefix="/api/v1/projects/{project_id}", tags=["overview"])


class Point(ApiModel):
    run_id: uuid.UUID
    at: datetime
    percent: float


class Overview(ApiModel):
    current_import: ImportOut | None
    units: int
    untested_units: int
    tests: dict[str, int]
    rejected_tests: int
    runs_total: int
    runs_by_status: dict[str, int]
    pass_rate: float | None
    latest_run: RunOut | None
    recent_runs: list[RunOut]
    coverage_percent: float | None
    coverage_trend: list[Point]


@router.get(
    "/overview",
    response_model=Overview,
    summary="Tests, pass and fail, coverage trend and untested code",
)
async def overview(p: Viewer, session: SessionDep) -> Overview:
    try:
        imp = await sources.current_import(session, p.project)
    except AppError:
        imp = None
    untested = len(await sources.units(session, imp.id, untested=True)) if imp else 0
    by_status = {
        str(s): int(n)
        for s, n in (
            await session.execute(
                select(TestRun.status, func.count())
                .where(TestRun.project_id == p.project_id)
                .group_by(TestRun.status)
            )
        ).all()
    }
    finished = sum(by_status.get(s, 0) for s in ("passed", "failed", "error", "limit_exceeded"))
    recent = await runs.list_runs(session, p.project_id, limit=10)
    trend = await coverage.trend(session, p.project_id, 30)
    rejected = int(
        await session.scalar(
            select(func.coalesce(func.sum(Generation.rejected_count), 0)).where(
                Generation.project_id == p.project_id
            )
        )
        or 0
    )
    latest = next((r for r in recent if runs.is_final(r)), None)
    return Overview(
        current_import=ImportOut.model_validate(imp) if imp else None,
        units=(imp.summary or {}).get("units", 0) if imp else 0,
        untested_units=untested,
        tests=await generation.counts(session, p.project_id),
        rejected_tests=rejected,
        runs_total=sum(by_status.values()),
        runs_by_status=by_status,
        pass_rate=round(100.0 * by_status.get("passed", 0) / finished, 1) if finished else None,
        latest_run=RunOut.model_validate(latest) if latest else None,
        recent_runs=[RunOut.model_validate(r) for r in recent],
        coverage_percent=trend[-1].line_percent if trend else None,
        coverage_trend=[
            Point(run_id=c.run_id, at=c.created_at, percent=c.line_percent) for c in trend
        ],
    )
