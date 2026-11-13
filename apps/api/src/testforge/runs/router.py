"""Test runs in the sandbox, their results and their history."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Query

from testforge.core.deps import ContainerDep, SessionDep
from testforge.core.errors import RateLimitedError
from testforge.jobs import queue
from testforge.projects.access import Executor, Viewer
from testforge.runs import service
from testforge.runs.models import TestRun
from testforge.runs.schemas import CaseOut, RunCreate, RunDetail, RunOut

router = APIRouter(prefix="/api/v1/projects/{project_id}/runs", tags=["runs"])


async def _detail(session: SessionDep, run: TestRun) -> RunDetail:
    out = RunDetail.model_validate(run)
    out.cases = [CaseOut.model_validate(c) for c in await service.cases(session, run.id)]
    return out


@router.post(
    "",
    response_model=RunDetail,
    status_code=202,
    summary="Run tests in the sandbox: generated tests, the project's own suite, or both",
    description="Every run executes in the sandbox service: no network, no credentials, and the "
    "project's CPU, memory, output and wall clock budget. A run that crosses a limit is stopped "
    "and reported with the limit it crossed (`limit_exceeded`). Pass `wait` (seconds) to return "
    "when it is done.",
)
async def create_run(
    body: RunCreate,
    p: Executor,
    session: SessionDep,
    container: ContainerDep,
    wait: float = Query(0, ge=0, le=900),
) -> RunDetail:
    try:
        decision = await container.kv.hit(f"run:{p.project_id}", container.settings.run_rpm)
    except Exception:
        decision = None
    if decision is not None and not decision.allowed:
        raise RateLimitedError(
            "Too many runs for this project in the last minute. Wait and try again",
            headers={"retry-after": str(decision.retry_after_s)},
        )
    run = await service.create(
        container,
        session,
        p,
        kind=body.kind,
        test_ids=body.test_ids,
        import_id=body.import_id,
        language=body.language,
        trigger="api" if p.key else "manual",
    )
    if wait:
        await queue.wait_for(container, run.id, wait)
        await session.refresh(run)
    return await _detail(session, run)


@router.get("", response_model=list[RunOut], summary="Run history, newest first")
async def list_runs(
    p: Viewer,
    session: SessionDep,
    status: str | None = Query(
        None, pattern=r"^(queued|running|passed|failed|error|limit_exceeded)$"
    ),
    before: datetime | None = None,
    limit: int = Query(50, ge=1, le=200),
) -> list[TestRun]:
    return list(
        await service.list_runs(session, p.project_id, status=status, limit=limit, before=before)
    )


@router.get(
    "/{run_id}",
    response_model=RunDetail,
    summary="One run: measurements, every test case, failures explained",
)
async def get_run(
    run_id: uuid.UUID,
    p: Viewer,
    session: SessionDep,
    container: ContainerDep,
    wait: float = Query(0, ge=0, le=900),
) -> RunDetail:
    run = await service.get(session, p.project_id, run_id)
    if wait and not service.is_final(run):
        await queue.wait_for(container, run.id, wait)
        await session.refresh(run)
    return await _detail(session, run)
