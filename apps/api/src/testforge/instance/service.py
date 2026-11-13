"""Instance settings and self sign-up.

Settings live in one row, created with safe defaults on first read (sign-up closed). A new
account always gets an organization of its own, which it owns; the first account on a fresh
instance is also the instance admin.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from testforge.audit.service import Actor, audit
from testforge.core.errors import AppError, ConflictError, PermissionDeniedError
from testforge.core.security import hash_password, password_problems
from testforge.instance.models import SINGLETON_ID, InstanceSettings
from testforge.instance.schemas import AdminSettings, PublicSettings, SettingsUpdate, SignupRequest
from testforge.orgs import service as orgs
from testforge.users.models import User


async def get(session: AsyncSession) -> InstanceSettings:
    row = await session.get(InstanceSettings, SINGLETON_ID)
    if row is None:
        await session.execute(
            insert(InstanceSettings).values(id=SINGLETON_ID).on_conflict_do_nothing()
        )
        await session.commit()
        row = await session.get(InstanceSettings, SINGLETON_ID)
    assert row is not None
    return row


def public(row: InstanceSettings) -> PublicSettings:
    return PublicSettings(site_name=row.site_name, allow_signup=row.allow_signup)


def admin(row: InstanceSettings) -> AdminSettings:
    return AdminSettings(site_name=row.site_name, allow_signup=row.allow_signup)


async def update(session: AsyncSession, data: SettingsUpdate, actor: Actor) -> InstanceSettings:
    row = await get(session)
    changes = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
    for field, value in changes.items():
        setattr(row, field, value)
    audit(
        session,
        actor,
        "instance.settings_updated",
        "instance_settings",
        row.id,
        fields=sorted(changes),
    )
    await session.commit()
    await session.refresh(row)
    return row


async def signup(session: AsyncSession, data: SignupRequest, ip: str | None) -> User:
    """An account and its own organization, when the instance allows people to register
    themselves. The first account on a fresh instance is always allowed and becomes the
    instance admin."""
    row = await get(session)
    first = not await session.scalar(select(User.id).limit(1))
    if not row.allow_signup and not first:
        raise PermissionDeniedError(
            "Sign-up is closed. Ask an administrator for an account", code="signup_closed"
        )
    if problems := password_problems(data.password):
        raise AppError(
            "Password needs " + ", ".join(problems),
            code="weak_password",
            details={"problems": problems},
        )
    if await session.scalar(select(User.id).where(func.lower(User.email) == data.email.lower())):
        raise ConflictError(
            "An account with this email exists. Sign in instead", code="email_taken"
        )
    user = User(
        email=data.email.lower(),
        name=data.name.strip(),
        role="admin" if first else "user",
        password_hash=await asyncio.to_thread(hash_password, data.password),
    )
    session.add(user)
    await session.flush()
    actor = Actor(user.id, user.email, user.role, ip)
    audit(session, actor, "auth.signup", "user", user.id)
    await orgs.create_for(session, user, data.organization or f"{user.name}'s organization", actor)
    await session.commit()
    await session.refresh(user)
    return user
