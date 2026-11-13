"""HTTP endpoints for organizations and their members."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Response

from testforge.auth.dependencies import CurrentUser, actor_of
from testforge.core.deps import SessionDep
from testforge.orgs import service
from testforge.orgs.schemas import (
    OrgCreate,
    OrgMemberAdd,
    OrgMemberOut,
    OrgMemberUpdate,
    OrgOut,
    OrgUpdate,
)

router = APIRouter(prefix="/api/v1/orgs", tags=["organizations"])


def _member(m: object, u: object) -> OrgMemberOut:
    return OrgMemberOut(
        user_id=u.id,  # type: ignore[attr-defined]
        email=u.email,  # type: ignore[attr-defined]
        name=u.name,  # type: ignore[attr-defined]
        role=m.role,  # type: ignore[attr-defined]
        created_at=m.created_at,  # type: ignore[attr-defined]
    )


@router.get("", response_model=list[OrgOut], summary="Organizations you belong to")
async def list_orgs(user: CurrentUser, session: SessionDep) -> list[OrgOut]:
    return await service.list_for(session, user)


@router.post("", response_model=OrgOut, status_code=201, summary="Create an organization you own")
async def create_org(body: OrgCreate, user: CurrentUser, session: SessionDep) -> OrgOut:
    org = await service.create_for(session, user, body.name, actor_of(user))
    await session.commit()
    return OrgOut.model_validate(org).model_copy(update={"role": "owner", "members": 1})


@router.get("/{org_id}", response_model=OrgOut, summary="An organization")
async def get_org(org_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> OrgOut:
    org, role = await service.get_for(session, user, org_id, "member")
    return next(o for o in await service.list_for(session, user) if o.id == org.id).model_copy(
        update={"role": role}
    )


@router.patch("/{org_id}", response_model=OrgOut, summary="Rename an organization (admins)")
async def update_org(
    org_id: uuid.UUID, body: OrgUpdate, user: CurrentUser, session: SessionDep
) -> OrgOut:
    org, role = await service.get_for(session, user, org_id, "admin")
    if body.name:
        org = await service.rename(session, org, body.name, actor_of(user))
    return OrgOut.model_validate(org).model_copy(update={"role": role})


@router.get(
    "/{org_id}/members", response_model=list[OrgMemberOut], summary="People in an organization"
)
async def list_members(
    org_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> list[OrgMemberOut]:
    org, _ = await service.get_for(session, user, org_id, "member")
    return [_member(m, u) for m, u in await service.members(session, org.id)]


@router.post(
    "/{org_id}/members",
    response_model=OrgMemberOut,
    status_code=201,
    summary="Add a person (creating their account if needed; admins)",
)
async def add_member(
    org_id: uuid.UUID, body: OrgMemberAdd, user: CurrentUser, session: SessionDep
) -> OrgMemberOut:
    org, role = await service.get_for(session, user, org_id, "admin")
    m, u = await service.add_member(session, org, body, actor_of(user), role)
    return _member(m, u)


@router.patch(
    "/{org_id}/members/{user_id}",
    response_model=OrgMemberOut,
    summary="Change a person's role (admins)",
)
async def update_member(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    body: OrgMemberUpdate,
    user: CurrentUser,
    session: SessionDep,
) -> OrgMemberOut:
    org, role = await service.get_for(session, user, org_id, "admin")
    await service.update_member(session, org, user_id, body.role, actor_of(user), role)
    rows = {u.id: (m, u) for m, u in await service.members(session, org.id)}
    return _member(*rows[user_id])


@router.delete("/{org_id}/members/{user_id}", status_code=204, summary="Remove a person (admins)")
async def remove_member(
    org_id: uuid.UUID, user_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> Response:
    org, role = await service.get_for(session, user, org_id, "admin")
    await service.remove_member(session, org, user_id, actor_of(user), role)
    return Response(status_code=204)
