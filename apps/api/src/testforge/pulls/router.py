"""GitHub pull request imports and the units their changes touch."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from testforge.core.deps import ContainerDep, SessionDep
from testforge.jobs import queue
from testforge.projects.access import Editor, Viewer
from testforge.pulls import service
from testforge.pulls.models import PullRequestImport
from testforge.pulls.schemas import PullCreate, PullDetail, PullOut
from testforge.sources import service as sources
from testforge.sources.schemas import UnitOut

router = APIRouter(prefix="/api/v1/projects/{project_id}/pulls", tags=["pull requests"])


async def _detail(session: SessionDep, pull: PullRequestImport) -> PullDetail:
    out = PullDetail.model_validate(pull)
    if pull.import_id and pull.scoped_unit_ids:
        rows = await sources.units(
            session, pull.import_id, ids=[uuid.UUID(u) for u in pull.scoped_unit_ids]
        )
        out.scoped_units = [UnitOut.model_validate(u) for u in rows]
    return out


@router.post(
    "",
    response_model=PullDetail,
    status_code=202,
    summary="Import a pull request: its changed files, and its head commit analyzed",
    description="Lists the files changed between the pull request's base and head and, once the "
    "head commit is analyzed, the functions, methods and routes those changes touch. Generate "
    "tests for exactly those with `POST .../tests/generate` and `pull_id`.",
)
async def create_pull(
    body: PullCreate,
    p: Editor,
    session: SessionDep,
    container: ContainerDep,
    wait: float = Query(0, ge=0, le=120),
) -> PullDetail:
    pull = await service.create(container, session, p, body.number, body.repo)
    if wait and pull.import_id and pull.status != "ready":
        await queue.wait_for(container, pull.import_id, wait)
        await session.refresh(pull)
    return await _detail(session, pull)


@router.get("", response_model=list[PullOut], summary="Imported pull requests")
async def list_pulls(p: Viewer, session: SessionDep) -> list[PullRequestImport]:
    return list(await service.list_pulls(session, p.project_id))


@router.get(
    "/{pull_id}", response_model=PullDetail, summary="One pull request and its scoped units"
)
async def get_pull(pull_id: uuid.UUID, p: Viewer, session: SessionDep) -> PullDetail:
    return await _detail(session, await service.get(session, p.project_id, pull_id))
