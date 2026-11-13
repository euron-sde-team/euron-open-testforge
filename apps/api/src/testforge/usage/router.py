from __future__ import annotations

from fastapi import APIRouter, Query

from testforge.core.deps import SessionDep
from testforge.projects.access import Viewer
from testforge.usage import service
from testforge.usage.schemas import UsageReport

router = APIRouter(prefix="/api/v1/projects/{project_id}/usage", tags=["usage"])


@router.get(
    "",
    response_model=UsageReport,
    summary="Generations, tests, runs, sandbox time and tokens by day and model",
)
async def usage(p: Viewer, session: SessionDep, days: int = Query(30, ge=1, le=366)) -> UsageReport:
    return await service.report(session, p.project_id, days)
