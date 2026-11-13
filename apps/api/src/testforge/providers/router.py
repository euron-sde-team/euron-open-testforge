"""HTTP endpoints for model providers (admins manage them; everyone sees which exist)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Response

from testforge.core.deps import ContainerDep, SessionDep
from testforge.projects.access import Admin, Viewer
from testforge.providers import service
from testforge.providers.schemas import ProviderCreate, ProviderOut, ProviderTest, ProviderUpdate

router = APIRouter(prefix="/api/v1/projects/{project_id}/providers", tags=["providers"])


@router.get("", response_model=list[ProviderOut], summary="Model providers of the project")
async def list_providers(
    p: Viewer, session: SessionDep, container: ContainerDep
) -> list[ProviderOut]:
    return await service.list_providers(container, session, p.project_id)


@router.post(
    "",
    response_model=ProviderOut,
    status_code=201,
    summary="Add a model provider with your own key (admins). The first one becomes the default",
)
async def create_provider(
    body: ProviderCreate, p: Admin, session: SessionDep, container: ContainerDep
) -> ProviderOut:
    row = await service.create_provider(container, session, p, body)
    return await service.provider_out(container, row)


@router.patch("/{provider_id}", response_model=ProviderOut, summary="Change a provider (admins)")
async def update_provider(
    provider_id: uuid.UUID,
    body: ProviderUpdate,
    p: Admin,
    session: SessionDep,
    container: ContainerDep,
) -> ProviderOut:
    row = await service.get_provider(session, p.project_id, provider_id)
    row = await service.update_provider(container, session, p, row, body)
    return await service.provider_out(container, row)


@router.delete("/{provider_id}", status_code=204, summary="Remove a provider (admins)")
async def delete_provider(provider_id: uuid.UUID, p: Admin, session: SessionDep) -> Response:
    row = await service.get_provider(session, p.project_id, provider_id)
    await service.delete_provider(session, p, row)
    return Response(status_code=204)


@router.post(
    "/{provider_id}/test",
    response_model=ProviderTest,
    summary="Test a provider: list its models with the stored key (admins)",
)
async def test_provider(
    provider_id: uuid.UUID, p: Admin, session: SessionDep, container: ContainerDep
) -> ProviderTest:
    row = await service.get_provider(session, p.project_id, provider_id)
    return await service.test_provider(container, session, row)
