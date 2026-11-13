"""Projects, members and API keys. Guards keep at least one admin in every project, and
project members are always people of the project's organization."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from testforge.audit.service import Actor, audit
from testforge.core import mail
from testforge.core.config import Settings
from testforge.core.errors import AppError, ConflictError, NotFoundError, PermissionDeniedError
from testforge.core.sealing import KeySealer
from testforge.core.security import generate_api_key
from testforge.core.text import slugify
from testforge.orgs import service as orgs
from testforge.orgs.models import OrgMember
from testforge.projects.access import Principal
from testforge.projects.models import ApiKey, Project, ProjectMember
from testforge.projects.schemas import (
    ApiKeyCreate,
    MemberAdd,
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
)
from testforge.sources.github import parse_repo
from testforge.users.models import User

log = logging.getLogger("testforge.projects")


async def unique_slug(session: AsyncSession, org_id: uuid.UUID, base: str) -> str:
    slug, n = base, 2
    while await session.scalar(
        select(Project.id).where(Project.org_id == org_id, Project.slug == slug)
    ):
        slug = f"{base[:56]}-{n}"
        n += 1
    return slug


async def list_projects(
    session: AsyncSession, user: User, org_id: uuid.UUID | None = None
) -> list[ProjectOut]:
    """Every project the user can see (all projects of organizations they administer, the
    others they are a member of), with their role, test count and latest run, in three
    queries whatever the number of projects."""
    from testforge.generation.models import GeneratedTest
    from testforge.runs.models import TestRun

    if user.role == "admin":
        stmt = select(Project, literal("admin"))
    else:
        admin_orgs = select(OrgMember.org_id).where(
            OrgMember.user_id == user.id, OrgMember.role.in_(("owner", "admin"))
        )
        stmt = (
            select(Project, func.coalesce(ProjectMember.role, "admin"))
            .outerjoin(
                ProjectMember,
                (ProjectMember.project_id == Project.id) & (ProjectMember.user_id == user.id),
            )
            .where(Project.org_id.in_(admin_orgs) | ProjectMember.user_id.is_not(None))
        )
    if org_id is not None:
        stmt = stmt.where(Project.org_id == org_id)
    rows = [(p, str(r)) for p, r in (await session.execute(stmt.order_by(Project.name))).all()]
    ids = [p.id for p, _ in rows]
    tests: dict[uuid.UUID, int] = {}
    last: dict[uuid.UUID, tuple[str, float | None]] = {}
    if ids:
        tests = {
            k: int(v)
            for k, v in (
                await session.execute(
                    select(GeneratedTest.project_id, func.count())
                    .where(GeneratedTest.project_id.in_(ids), GeneratedTest.status == "accepted")
                    .group_by(GeneratedTest.project_id)
                )
            ).all()
        }
        latest = (
            select(TestRun.project_id, TestRun.status, TestRun.coverage_percent)
            .where(TestRun.project_id.in_(ids), TestRun.finished_at.is_not(None))
            .distinct(TestRun.project_id)
            .order_by(TestRun.project_id, TestRun.finished_at.desc())
        )
        last = {pid: (status, cov) for pid, status, cov in (await session.execute(latest)).all()}
    return [
        project_out(p, role).model_copy(
            update={
                "tests": tests.get(p.id, 0),
                "last_run_status": last.get(p.id, (None, None))[0],
                "coverage_percent": last.get(p.id, (None, None))[1],
            }
        )
        for p, role in rows
    ]


def project_out(project: Project, role: str) -> ProjectOut:
    return ProjectOut.model_validate(project).model_copy(
        update={"role": role, "has_github_token": project.github_token_sealed is not None}
    )


async def create_project(
    session: AsyncSession, data: ProjectCreate, user: User, actor: Actor
) -> Project:
    org, _ = await orgs.get_for(session, user, data.org_id, "admin")
    slug = data.slug or slugify(data.name, "project")
    if data.slug and await session.scalar(
        select(Project.id).where(Project.org_id == org.id, Project.slug == data.slug)
    ):
        raise ConflictError("A project with this slug exists", code="slug_taken")
    project = Project(
        org_id=org.id,
        name=data.name.strip(),
        slug=await unique_slug(session, org.id, slug),
        description=data.description,
        created_by=user.id,
    )
    session.add(project)
    await session.flush()
    session.add(ProjectMember(project_id=project.id, user_id=user.id, role="admin"))
    audit(
        session,
        actor,
        "project.created",
        "project",
        project.id,
        name=project.name,
        org_id=org.id,
        project_id=project.id,
    )
    await session.commit()
    return project


async def update_project(
    session: AsyncSession, sealer: KeySealer, p: Principal, data: ProjectUpdate
) -> Project:
    project = p.project
    changes = data.model_dump(exclude_unset=True)
    token = changes.pop("github_token", None)
    if "github_repo" in changes:
        repo = changes.pop("github_repo")
        try:
            project.github_repo = parse_repo(repo) if repo else None
        except ValueError as exc:
            raise AppError(str(exc), code="invalid_repo") from None
    for field in ("name", "description"):
        if changes.get(field) is None:
            changes.pop(field, None)
    for field, value in changes.items():
        setattr(project, field, value)
    if token is not None:
        project.github_token_sealed = (
            await sealer.seal(token, f"project:{project.id}:github_token") if token else None
        )
        changes["github_token"] = "set" if token else "removed"
    if "github_repo" in data.model_fields_set:
        changes["github_repo"] = project.github_repo
    audit(
        session,
        p.actor,
        "project.updated",
        "project",
        project.id,
        fields=sorted(changes),
        **p.audit_scope(),
    )
    await session.commit()
    await session.refresh(project)
    return project


async def delete_project(session: AsyncSession, p: Principal) -> None:
    audit(
        session,
        p.actor,
        "project.deleted",
        "project",
        p.project_id,
        name=p.project.name,
        org_id=p.org_id,
    )
    await session.delete(p.project)
    await session.commit()


async def members(
    session: AsyncSession, project_id: uuid.UUID
) -> Sequence[tuple[ProjectMember, User]]:
    result = await session.execute(
        select(ProjectMember, User)
        .join(User, User.id == ProjectMember.user_id)
        .where(ProjectMember.project_id == project_id)
        .order_by(User.name)
    )
    return [(m, u) for m, u in result.all()]


async def add_member(
    session: AsyncSession, p: Principal, data: MemberAdd
) -> tuple[ProjectMember, User]:
    user = await session.scalar(select(User).where(func.lower(User.email) == data.email.lower()))
    in_org = await session.get(OrgMember, (p.org_id, user.id)) if user is not None else None
    if user is None or in_org is None:
        raise NotFoundError(
            "Nobody in this organization has this email. Add them to the organization first",
            code="user_not_found",
        )
    if await session.get(ProjectMember, (p.project_id, user.id)):
        raise ConflictError("This person is already a member", code="already_member")
    member = ProjectMember(project_id=p.project_id, user_id=user.id, role=data.role)
    session.add(member)
    audit(
        session,
        p.actor,
        "project.member_added",
        "project",
        p.project_id,
        user=user.email,
        role=data.role,
        **p.audit_scope(),
    )
    await session.commit()
    await session.refresh(member)
    return member, user


ROLE_WORDS = {
    "viewer": "read its source analysis, generated tests, runs and coverage",
    "editor": "import code, generate and review tests and run them in the sandbox",
    "admin": "do everything an editor does and manage members, API keys and model providers",
}


async def notify_member(settings: Settings, p: Principal, user: User, role: str) -> None:
    """Tell a person they were added to a project. Best effort: a mail outage never undoes
    the membership (it is logged and the admin can share the link themselves)."""
    link = f"{settings.public_url.rstrip('/')}/projects/{p.project_id}"
    text = (
        f"Hello {user.name},\n\n{p.actor.email or 'An admin'} added you to the TestForge "
        f"project {p.project.name} as {role}. You can now {ROLE_WORDS.get(role, 'use it')}.\n\n"
        f"Open it: {link}\n"
    )
    try:
        await mail.send(settings, user.email, f"You were added to {p.project.name}", text)
    except mail.MailError:
        log.warning("member notice not sent", extra={"project": str(p.project_id)})


async def _owners(session: AsyncSession, project_id: uuid.UUID) -> int:
    rows = await session.scalars(
        select(ProjectMember.user_id)
        .where(ProjectMember.project_id == project_id, ProjectMember.role == "admin")
        .with_for_update()
    )
    return len(rows.all())


async def update_member(
    session: AsyncSession, p: Principal, user_id: uuid.UUID, role: str
) -> ProjectMember:
    member = await session.get(ProjectMember, (p.project_id, user_id))
    if member is None:
        raise NotFoundError("Member not found")
    if member.role == "admin" and role != "admin" and await _owners(session, p.project_id) <= 1:
        raise ConflictError("A project needs at least one admin", code="last_admin")
    member.role = role
    audit(
        session,
        p.actor,
        "project.member_updated",
        "project",
        p.project_id,
        user_id=str(user_id),
        role=role,
        **p.audit_scope(),
    )
    await session.commit()
    return member


async def remove_member(session: AsyncSession, p: Principal, user_id: uuid.UUID) -> None:
    member = await session.get(ProjectMember, (p.project_id, user_id))
    if member is None:
        raise NotFoundError("Member not found")
    if member.role == "admin" and await _owners(session, p.project_id) <= 1:
        raise ConflictError("A project needs at least one admin", code="last_admin")
    await session.delete(member)
    audit(
        session,
        p.actor,
        "project.member_removed",
        "project",
        p.project_id,
        user_id=str(user_id),
        **p.audit_scope(),
    )
    await session.commit()


async def list_keys(session: AsyncSession, project_id: uuid.UUID) -> Sequence[ApiKey]:
    return (
        await session.scalars(
            select(ApiKey).where(ApiKey.project_id == project_id).order_by(ApiKey.created_at.desc())
        )
    ).all()


async def create_key(
    session: AsyncSession, p: Principal, data: ApiKeyCreate, pepper: str
) -> tuple[ApiKey, str]:
    if p.key is not None:
        raise PermissionDeniedError(
            "API keys cannot create API keys", code="key_cannot_create_keys"
        )
    generated = generate_api_key(pepper)
    key = ApiKey(
        project_id=p.project_id,
        name=data.name.strip(),
        prefix=generated.prefix,
        secret_hash=generated.secret_hash,
        scopes=list(data.scopes),
        created_by=p.user_id,
    )
    session.add(key)
    await session.flush()
    audit(
        session,
        p.actor,
        "api_key.created",
        "api_key",
        key.id,
        name=key.name,
        scopes=key.scopes,
        **p.audit_scope(),
    )
    await session.commit()
    await session.refresh(key)
    return key, generated.plaintext


async def revoke_key(session: AsyncSession, p: Principal, key_id: uuid.UUID) -> ApiKey:
    key = await session.scalar(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.project_id == p.project_id)
    )
    if key is None:
        raise NotFoundError("API key not found")
    if key.revoked_at is None:
        key.revoked_at = datetime.now(UTC)
        audit(
            session, p.actor, "api_key.revoked", "api_key", key.id, name=key.name, **p.audit_scope()
        )
        await session.commit()
    return key
