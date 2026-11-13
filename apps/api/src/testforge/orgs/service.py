"""Organizations (tenants) and their members.

Isolation is structural: projects carry ``org_id``, and every import, code unit, generated
test, run, coverage report, provider and usage row is reached through its project, which
``projects.access`` resolves only for people in that project's organization (or API keys
of that project). Guards keep at least one owner in every organization.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from testforge.audit.service import Actor, audit
from testforge.core.errors import AppError, ConflictError, NotFoundError, PermissionDeniedError
from testforge.core.security import hash_password, password_problems
from testforge.core.text import slugify
from testforge.orgs.models import Organization, OrgMember
from testforge.orgs.schemas import OrgMemberAdd, OrgOut
from testforge.users.models import User

ORG_RANK = {"member": 0, "admin": 1, "owner": 2}


async def unique_slug(session: AsyncSession, base: str) -> str:
    slug, n = base, 2
    while await session.scalar(select(Organization.id).where(Organization.slug == slug)):
        slug = f"{base[:56]}-{n}"
        n += 1
    return slug


async def create_for(session: AsyncSession, user: User, name: str, actor: Actor) -> Organization:
    """A new organization owned by ``user`` (flushed, not committed)."""
    org = Organization(
        name=name.strip()[:120],
        slug=await unique_slug(session, slugify(name, "org")),
        created_by=user.id,
    )
    session.add(org)
    await session.flush()
    session.add(OrgMember(org_id=org.id, user_id=user.id, role="owner"))
    audit(session, actor, "org.created", "organization", org.id, name=org.name, org_id=org.id)
    return org


async def role_in(session: AsyncSession, user: User, org_id: uuid.UUID) -> str | None:
    """The user's role in the organization; instance admins are owners everywhere."""
    if user.role == "admin":
        return "owner"
    member = await session.get(OrgMember, (org_id, user.id))
    return member.role if member else None


async def get_for(
    session: AsyncSession, user: User, org_id: uuid.UUID, at_least: str
) -> tuple[Organization, str]:
    """The organization and the user's role in it, or 404 when they are not in it (its
    existence does not leak), or 403 when their role is below ``at_least``."""
    org = await session.get(Organization, org_id)
    role = await role_in(session, user, org_id) if org else None
    if org is None or role is None:
        raise NotFoundError("Organization not found")
    if ORG_RANK[role] < ORG_RANK[at_least]:
        raise PermissionDeniedError(
            f"This needs the {at_least} role in the organization", code="insufficient_org_role"
        )
    return org, role


async def list_for(session: AsyncSession, user: User) -> list[OrgOut]:
    from testforge.projects.models import Project

    if user.role == "admin":
        rows = [
            (o, "owner")
            for o in (await session.scalars(select(Organization).order_by(Organization.name))).all()
        ]
    else:
        result = await session.execute(
            select(Organization, OrgMember.role)
            .join(OrgMember, OrgMember.org_id == Organization.id)
            .where(OrgMember.user_id == user.id)
            .order_by(Organization.name)
        )
        rows = [(o, str(r)) for o, r in result.all()]
    ids = [o.id for o, _ in rows]
    projects: dict[uuid.UUID, int] = {}
    members: dict[uuid.UUID, int] = {}
    if ids:
        projects = {
            k: int(v)
            for k, v in (
                await session.execute(
                    select(Project.org_id, func.count())
                    .where(Project.org_id.in_(ids))
                    .group_by(Project.org_id)
                )
            ).all()
        }
        members = {
            k: int(v)
            for k, v in (
                await session.execute(
                    select(OrgMember.org_id, func.count())
                    .where(OrgMember.org_id.in_(ids))
                    .group_by(OrgMember.org_id)
                )
            ).all()
        }
    return [
        OrgOut.model_validate(o).model_copy(
            update={
                "role": role,
                "projects": projects.get(o.id, 0),
                "members": members.get(o.id, 0),
            }
        )
        for o, role in rows
    ]


async def rename(session: AsyncSession, org: Organization, name: str, actor: Actor) -> Organization:
    org.name = name.strip()
    audit(session, actor, "org.updated", "organization", org.id, name=org.name, org_id=org.id)
    await session.commit()
    await session.refresh(org)
    return org


async def members(session: AsyncSession, org_id: uuid.UUID) -> Sequence[tuple[OrgMember, User]]:
    result = await session.execute(
        select(OrgMember, User)
        .join(User, User.id == OrgMember.user_id)
        .where(OrgMember.org_id == org_id)
        .order_by(User.name)
    )
    return [(m, u) for m, u in result.all()]


async def add_member(
    session: AsyncSession, org: Organization, data: OrgMemberAdd, actor: Actor, caller_role: str
) -> tuple[OrgMember, User]:
    if data.role == "owner" and caller_role != "owner":
        raise PermissionDeniedError("Only owners can add owners", code="insufficient_org_role")
    user = await session.scalar(select(User).where(func.lower(User.email) == data.email.lower()))
    if user is None:
        if not (data.name and data.password):
            raise NotFoundError(
                "No account has this email. Give a name and a temporary password to create one",
                code="user_not_found",
            )
        if problems := password_problems(data.password):
            raise AppError(
                "Password needs " + ", ".join(problems),
                code="weak_password",
                details={"problems": problems},
            )
        user = User(
            email=data.email.lower(),
            name=data.name.strip(),
            role="user",
            password_hash=await asyncio.to_thread(hash_password, data.password),
        )
        session.add(user)
        await session.flush()
        audit(session, actor, "user.created", "user", user.id, email=user.email, org_id=org.id)
    elif await session.get(OrgMember, (org.id, user.id)):
        raise ConflictError("This person is already in the organization", code="already_member")
    member = OrgMember(org_id=org.id, user_id=user.id, role=data.role)
    session.add(member)
    audit(
        session,
        actor,
        "org.member_added",
        "organization",
        org.id,
        user=user.email,
        role=data.role,
        org_id=org.id,
    )
    await session.commit()
    await session.refresh(member)
    return member, user


async def _owners(session: AsyncSession, org_id: uuid.UUID) -> int:
    rows = await session.scalars(
        select(OrgMember.user_id)
        .where(OrgMember.org_id == org_id, OrgMember.role == "owner")
        .with_for_update()
    )
    return len(rows.all())


async def update_member(
    session: AsyncSession,
    org: Organization,
    user_id: uuid.UUID,
    role: str,
    actor: Actor,
    caller_role: str,
) -> OrgMember:
    member = await session.get(OrgMember, (org.id, user_id))
    if member is None:
        raise NotFoundError("Member not found")
    if "owner" in (role, member.role) and caller_role != "owner":
        raise PermissionDeniedError("Only owners can change owners", code="insufficient_org_role")
    if member.role == "owner" and role != "owner" and await _owners(session, org.id) <= 1:
        raise ConflictError("An organization needs at least one owner", code="last_owner")
    member.role = role
    audit(
        session,
        actor,
        "org.member_updated",
        "organization",
        org.id,
        user_id=str(user_id),
        role=role,
        org_id=org.id,
    )
    await session.commit()
    return member


async def remove_member(
    session: AsyncSession, org: Organization, user_id: uuid.UUID, actor: Actor, caller_role: str
) -> None:
    from testforge.projects.models import Project, ProjectMember

    member = await session.get(OrgMember, (org.id, user_id))
    if member is None:
        raise NotFoundError("Member not found")
    if member.role == "owner" and caller_role != "owner":
        raise PermissionDeniedError("Only owners can remove owners", code="insufficient_org_role")
    if member.role == "owner" and await _owners(session, org.id) <= 1:
        raise ConflictError("An organization needs at least one owner", code="last_owner")
    # Leaving the organization also leaves every project in it.
    project_ids = select(Project.id).where(Project.org_id == org.id).scalar_subquery()
    for pm in (
        await session.scalars(
            select(ProjectMember).where(
                ProjectMember.user_id == user_id, ProjectMember.project_id.in_(project_ids)
            )
        )
    ).all():
        await session.delete(pm)
    await session.delete(member)
    audit(
        session,
        actor,
        "org.member_removed",
        "organization",
        org.id,
        user_id=str(user_id),
        org_id=org.id,
    )
    await session.commit()
