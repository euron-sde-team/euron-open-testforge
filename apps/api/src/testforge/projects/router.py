from __future__ import annotations

import uuid

from fastapi import APIRouter, Request, Response

from testforge.auth.dependencies import CurrentUser
from testforge.core.deps import ContainerDep, SessionDep
from testforge.core.schemas import Ack
from testforge.projects import service
from testforge.projects.access import Admin, Current, Viewer
from testforge.projects.models import Project
from testforge.projects.schemas import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyOut,
    MemberAdd,
    MemberOut,
    MemberUpdate,
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
)

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


def _out(project: Project, role: str) -> ProjectOut:
    return service.project_out(project, role)


@router.get("", response_model=list[ProjectOut], summary="Projects you can see")
async def list_projects(
    user: CurrentUser, session: SessionDep, org_id: uuid.UUID | None = None
) -> list[ProjectOut]:
    return await service.list_projects(session, user, org_id)


@router.post(
    "",
    response_model=ProjectOut,
    status_code=201,
    summary="Create a project in an organization (admins; you become its admin)",
)
async def create_project(
    body: ProjectCreate, request: Request, user: CurrentUser, session: SessionDep
) -> ProjectOut:
    return _out(await service.create_project(session, body, user, request.state.actor), "admin")


@router.get(
    "/current",
    response_model=ProjectOut,
    summary="The project of the API key in use (or of the X-Project-Id header)",
    description="Lets the SDK and the CLI find their project from the key alone.",
)
async def current_project(p: Current) -> ProjectOut:
    return _out(p.project, p.role)


@router.get("/{project_id}", response_model=ProjectOut, summary="One project")
async def get_project(project_id: uuid.UUID, p: Viewer) -> ProjectOut:
    return _out(p.project, p.role)


@router.patch("/{project_id}", response_model=ProjectOut, summary="Change a project's settings")
async def update_project(
    project_id: uuid.UUID,
    body: ProjectUpdate,
    p: Admin,
    session: SessionDep,
    container: ContainerDep,
) -> ProjectOut:
    return _out(await service.update_project(session, container.sealer, p, body), p.role)


@router.delete("/{project_id}", status_code=204, summary="Delete a project and everything in it")
async def delete_project(project_id: uuid.UUID, p: Admin, session: SessionDep) -> Response:
    await service.delete_project(session, p)
    return Response(status_code=204)


@router.get("/{project_id}/members", response_model=list[MemberOut], summary="Project members")
async def list_members(project_id: uuid.UUID, p: Viewer, session: SessionDep) -> list[MemberOut]:
    return [
        MemberOut(user_id=u.id, email=u.email, name=u.name, role=m.role, created_at=m.created_at)
        for m, u in await service.members(session, p.project_id)
    ]


@router.post(
    "/{project_id}/members", response_model=MemberOut, status_code=201, summary="Add a member"
)
async def add_member(
    project_id: uuid.UUID, body: MemberAdd, p: Admin, session: SessionDep, container: ContainerDep
) -> MemberOut:
    m, u = await service.add_member(session, p, body)
    await service.notify_member(container.settings, p, u, m.role)
    return MemberOut(user_id=u.id, email=u.email, name=u.name, role=m.role, created_at=m.created_at)


@router.patch(
    "/{project_id}/members/{user_id}", response_model=Ack, summary="Change a member's role"
)
async def update_member(
    project_id: uuid.UUID, user_id: uuid.UUID, body: MemberUpdate, p: Admin, session: SessionDep
) -> Ack:
    await service.update_member(session, p, user_id, body.role)
    return Ack(message="Role updated")


@router.delete("/{project_id}/members/{user_id}", status_code=204, summary="Remove a member")
async def remove_member(
    project_id: uuid.UUID, user_id: uuid.UUID, p: Admin, session: SessionDep
) -> Response:
    await service.remove_member(session, p, user_id)
    return Response(status_code=204)


@router.get("/{project_id}/api-keys", response_model=list[ApiKeyOut], summary="API keys")
async def list_keys(project_id: uuid.UUID, p: Admin, session: SessionDep) -> list[ApiKeyOut]:
    return [ApiKeyOut.model_validate(k) for k in await service.list_keys(session, p.project_id)]


@router.post(
    "/{project_id}/api-keys",
    response_model=ApiKeyCreated,
    status_code=201,
    summary="Create an API key (shown once)",
)
async def create_key(
    project_id: uuid.UUID,
    body: ApiKeyCreate,
    p: Admin,
    session: SessionDep,
    container: ContainerDep,
) -> ApiKeyCreated:
    key, plaintext = await service.create_key(session, p, body, container.settings.api_key_pepper)
    return ApiKeyCreated(**ApiKeyOut.model_validate(key).model_dump(), key=plaintext)


@router.delete(
    "/{project_id}/api-keys/{key_id}", response_model=ApiKeyOut, summary="Revoke an API key"
)
async def revoke_key(
    project_id: uuid.UUID, key_id: uuid.UUID, p: Admin, session: SessionDep
) -> ApiKeyOut:
    return ApiKeyOut.model_validate(await service.revoke_key(session, p, key_id))
