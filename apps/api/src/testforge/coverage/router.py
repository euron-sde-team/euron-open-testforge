"""Coverage per run and per project over time."""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from testforge.core.deps import SessionDep
from testforge.core.errors import NotFoundError
from testforge.coverage import service
from testforge.coverage.models import CoverageReport
from testforge.coverage.schemas import CoverageOut, ProjectCoverage, TrendPoint
from testforge.projects.access import Viewer
from testforge.runs import service as runs

router = APIRouter(prefix="/api/v1/projects/{project_id}", tags=["coverage"])


@router.get(
    "/runs/{run_id}/coverage", response_model=CoverageOut, summary="Coverage measured in one run"
)
async def run_coverage(run_id: uuid.UUID, p: Viewer, session: SessionDep) -> CoverageReport:
    await runs.get(session, p.project_id, run_id)
    report = await service.for_run(session, run_id)
    if report is None:
        raise NotFoundError("This run has no coverage report (it did not finish, or measured none)")
    return report


@router.get(
    "/coverage",
    response_model=ProjectCoverage,
    summary="The latest coverage and the trend over runs",
)
async def project_coverage(p: Viewer, session: SessionDep) -> ProjectCoverage:
    points = await service.trend(session, p.project_id)
    return ProjectCoverage(
        latest=CoverageOut.model_validate(points[-1]) if points else None,
        trend=[TrendPoint.model_validate(r) for r in points],
    )
