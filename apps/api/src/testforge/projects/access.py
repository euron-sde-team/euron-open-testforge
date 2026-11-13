"""Who may do what in a project. Every project route resolves a ``Principal`` first.

The project comes from the path (``/projects/{project_id}/...``), from the API key (a key
belongs to one project), or from the ``X-Project-Id`` header.

People hold a project role (viewer < editor < admin). Owners and admins of the project's
organization, and instance admins, act as project admins. Viewers read imports, source
analysis, generated tests, runs, coverage and reports; editors also import code, generate
and review tests and start runs; admins also manage members, API keys, model providers,
webhooks and the GitHub connection. API keys carry scopes:

* ``read``: everything a viewer sees
* ``generate``: generate tests and analyze failures (a model is called)
* ``execute``: start runs in the sandbox
* ``manage``: import code and OpenAPI documents, accept or discard tests, webhooks (CI)

A project the caller cannot see answers 404, never 403, so its existence does not leak.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import Depends, Path, Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from testforge.audit.service import Actor
from testforge.auth.dependencies import api_key_from, current_user
from testforge.core.deps import ContainerDep, SessionDep, client_ip
from testforge.core.errors import (
    AppError,
    AuthenticationError,
    NotFoundError,
    PermissionDeniedError,
)
from testforge.core.security import constant_time_equals, hash_key_secret, parse_api_key
from testforge.orgs import service as orgs
from testforge.projects.models import ApiKey, Project, ProjectMember

ROLE_RANK = {"viewer": 0, "editor": 1, "admin": 2}
SCOPES = ("read", "generate", "execute", "manage")
PROJECT_HEADER = "x-project-id"
_TOUCH_EVERY = timedelta(minutes=5)


@dataclass(frozen=True)
class Principal:
    project: Project
    role: str  # viewer, editor, admin
    actor: Actor
    key: ApiKey | None = None

    @property
    def project_id(self) -> uuid.UUID:
        return self.project.id

    @property
    def org_id(self) -> uuid.UUID:
        return self.project.org_id

    @property
    def user_id(self) -> uuid.UUID | None:
        return None if self.key is not None else self.actor.id

    def at_least(self, role: str) -> bool:
        return ROLE_RANK[self.role] >= ROLE_RANK[role]

    def has_scope(self, scope: str) -> bool:
        return self.key is None or scope in (self.key.scopes or [])

    def audit_scope(self) -> dict[str, uuid.UUID]:
        """The tenant columns for an audit row written on this principal's behalf."""
        return {"org_id": self.org_id, "project_id": self.project_id}


async def _key(request: Request, session: AsyncSession, raw: str, pepper: str) -> ApiKey:
    parsed = parse_api_key(raw)
    if parsed is None:
        raise AuthenticationError("The API key is malformed", code="invalid_api_key")
    prefix, secret = parsed
    key = await session.scalar(select(ApiKey).where(ApiKey.prefix == prefix))
    if (
        key is None
        or key.revoked_at is not None
        or not constant_time_equals(key.secret_hash, hash_key_secret(secret, pepper))
    ):
        raise AuthenticationError("The API key is not valid", code="invalid_api_key")
    now = datetime.now(UTC)
    if key.last_used_at is None or now - key.last_used_at > _TOUCH_EVERY:
        await session.execute(update(ApiKey).where(ApiKey.id == key.id).values(last_used_at=now))
        await session.commit()
    request.state.actor = Actor(None, f"api-key:{key.name}", "api_key", client_ip(request))
    return key


def _header_project(request: Request) -> uuid.UUID | None:
    raw = request.headers.get(PROJECT_HEADER)
    if not raw:
        return None
    try:
        return uuid.UUID(raw)
    except ValueError:
        raise NotFoundError("Project not found") from None


async def resolve(
    request: Request,
    container: ContainerDep,
    session: SessionDep,
    project_id: uuid.UUID | None,
) -> Principal:
    raw_key = api_key_from(request)
    if raw_key:
        key = await _key(request, session, raw_key, container.settings.api_key_pepper)
        wanted = project_id or _header_project(request) or key.project_id
        if wanted != key.project_id:
            # A key for another project: the same answer as a project that does not exist.
            raise NotFoundError("Project not found")
        project = await session.get(Project, key.project_id)
        if project is None:
            raise NotFoundError("Project not found")
        writes = {"manage", "generate", "execute"} & set(key.scopes or [])
        role = "editor" if writes else "viewer"
        return Principal(project, role, request.state.actor, key)
    user = await current_user(request, container, session)
    chosen = project_id or _header_project(request)
    if chosen is None:
        raise AppError(
            "Choose a project: send its id in the X-Project-Id header, or use a project API key",
            code="project_required",
        )
    project = await session.get(Project, chosen)
    if project is None:
        raise NotFoundError("Project not found")
    org_role = await orgs.role_in(session, user, project.org_id)
    if org_role in ("owner", "admin"):
        role = "admin"
    else:
        member = await session.get(ProjectMember, (project.id, user.id)) if org_role else None
        if member is None:
            raise NotFoundError("Project not found")
        role = member.role
    return Principal(project, role, request.state.actor)


def _check(p: Principal, role: str, scope: str) -> Principal:
    if p.key is not None:
        if scope not in (p.key.scopes or []):
            raise PermissionDeniedError(
                f"This API key lacks the {scope!r} scope", code="insufficient_scope"
            )
        return p
    if not p.at_least(role):
        raise PermissionDeniedError(
            f"This action needs the {role} role in this project", code="insufficient_role"
        )
    return p


def project_role(role: str, scope: str = "read") -> Callable[..., Coroutine[Any, Any, Principal]]:
    """A dependency: the caller holds at least ``role`` in the path's project (people) or
    the ``scope`` (API keys). The path parameter is declared here, so every project route
    documents it in the OpenAPI document."""

    async def dependency(
        request: Request,
        container: ContainerDep,
        session: SessionDep,
        project_id: Annotated[uuid.UUID, Path(description="The project")],
    ) -> Principal:
        return _check(await resolve(request, container, session, project_id), role, scope)

    return dependency


async def _current(request: Request, container: ContainerDep, session: SessionDep) -> Principal:
    """The project an API key belongs to (or the ``X-Project-Id`` header's), for routes
    without a project in the path."""
    return _check(await resolve(request, container, session, None), "viewer", "read")


Viewer = Annotated[Principal, Depends(project_role("viewer", "read"))]
Editor = Annotated[Principal, Depends(project_role("editor", "manage"))]
Admin = Annotated[Principal, Depends(project_role("admin", "__admin_only__"))]
Generator = Annotated[Principal, Depends(project_role("editor", "generate"))]
Executor = Annotated[Principal, Depends(project_role("editor", "execute"))]
Current = Annotated[Principal, Depends(_current)]
