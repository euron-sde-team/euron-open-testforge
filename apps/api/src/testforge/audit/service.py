"""Append-only audit trail. Written in the same transaction as the change it describes,
so a change without an audit row cannot be committed."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testforge.audit.models import AuditLog


@dataclass(frozen=True, slots=True)
class Actor:
    id: uuid.UUID | None
    email: str | None
    role: str
    ip: str | None = None


def audit(
    session: AsyncSession,
    actor: Actor,
    action: str,
    target_type: str | None = None,
    target_id: object | None = None,
    **details: Any,
) -> None:
    """Record ``action``. ``org_id`` and ``project_id`` in ``details`` become the tenant
    columns of the row (and are not repeated in the details)."""
    org_id = details.pop("org_id", None)
    project_id = details.pop("project_id", None)
    session.add(
        AuditLog(
            actor_id=actor.id,
            actor_email=actor.email,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            details=details,
            ip=actor.ip,
            org_id=_uuid(org_id),
            project_id=_uuid(project_id),
        )
    )


def _uuid(value: object) -> uuid.UUID | None:
    if value is None or isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


async def list_entries(
    session: AsyncSession,
    after_id: int | None,
    limit: int,
    action: str | None,
    *,
    org_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    target_id: str | None = None,
    actor_id: uuid.UUID | None = None,
) -> list[AuditLog]:
    """Newest first, keyset-paginated on id; ``limit + 1`` rows so the caller can tell
    whether another page exists. ``action`` filters by prefix (``user.`` matches all).
    ``org_id`` or ``project_id`` scope the trail to one tenant; ``target_id`` keeps the
    entries about one record (a run, a test, an import), ``actor_id`` one person's."""
    stmt = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit + 1)
    if org_id is not None:
        stmt = stmt.where(AuditLog.org_id == org_id)
    if project_id is not None:
        stmt = stmt.where(AuditLog.project_id == project_id)
    if target_id is not None:
        stmt = stmt.where(AuditLog.target_id == target_id)
    if actor_id is not None:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    if after_id is not None:
        stmt = stmt.where(AuditLog.id < after_id)
    if action:
        stmt = stmt.where(AuditLog.action.startswith(action))
    return list((await session.scalars(stmt)).all())
