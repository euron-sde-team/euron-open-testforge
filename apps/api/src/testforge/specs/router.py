"""OpenAPI documents for API test generation."""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from testforge.core.deps import ContainerDep, SessionDep
from testforge.projects.access import Editor, Viewer
from testforge.specs import service
from testforge.specs.models import ApiSpec
from testforge.specs.schemas import SpecCreate, SpecOut

router = APIRouter(prefix="/api/v1/projects/{project_id}/specs", tags=["specs"])


@router.post(
    "",
    response_model=SpecOut,
    status_code=201,
    summary="Import an OpenAPI 3 document (JSON or YAML)",
)
async def create_spec(
    body: SpecCreate, p: Editor, session: SessionDep, container: ContainerDep
) -> ApiSpec:
    return await service.create(session, p, body.document, container.settings.max_spec_bytes)


@router.get("", response_model=list[SpecOut], summary="Imported OpenAPI documents")
async def list_specs(p: Viewer, session: SessionDep) -> list[ApiSpec]:
    return list(await service.list_specs(session, p.project_id))


@router.get("/{spec_id}", response_model=SpecOut, summary="One document and its operations")
async def get_spec(spec_id: uuid.UUID, p: Viewer, session: SessionDep) -> ApiSpec:
    return await service.get(session, p.project_id, spec_id)
