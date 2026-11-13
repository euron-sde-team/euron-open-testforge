"""Database engine, session factory and the declarative base shared by every domain."""

from __future__ import annotations

import asyncio
import random
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_id() -> uuid.UUID:
    return uuid.uuid4()


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSONB, list[str]: JSONB}


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Database:
    """Owns the engine and session factory for one application instance."""

    def __init__(self, url: str, *, pool_size: int = 10, max_overflow: int = 20) -> None:
        self.engine: AsyncEngine = create_async_engine(
            url,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_pre_ping=True,
            pool_recycle=1800,
            # Never echo bound values (password hashes, key hashes, content) into an
            # exception message, and so never into a log line.
            hide_parameters=True,
        )
        self.sessionmaker = async_sessionmaker(self.engine, expire_on_commit=False)

    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.sessionmaker() as session:
            yield session

    async def dispose(self) -> None:
        await self.engine.dispose()


def is_deadlock(exc: BaseException) -> bool:
    """A deadlock or serialization failure: Postgres aborted this transaction so another
    could proceed, and running it again is the expected remedy."""
    orig = getattr(exc, "orig", None)
    code = getattr(orig, "sqlstate", None) or getattr(
        getattr(orig, "__cause__", None), "sqlstate", None
    )
    return code in ("40P01", "40001")


async def retry_deadlocks[T](fn: Callable[[], Awaitable[T]], attempts: int = 5) -> T:
    """Run a short transaction again when Postgres resolves a deadlock against it."""
    for attempt in range(attempts):
        try:
            return await fn()
        except DBAPIError as exc:
            if not is_deadlock(exc) or attempt == attempts - 1:
                raise
            await asyncio.sleep(0.05 * (attempt + 1) + random.random() * 0.05)  # noqa: S311 jitter
    raise AssertionError("unreachable")


def import_all_models() -> None:
    """Import every domain's models so Base.metadata is complete (Alembic, tests)."""
    from testforge.audit import models as _audit  # noqa: F401
    from testforge.auth import models as _auth  # noqa: F401
    from testforge.coverage import models as _coverage  # noqa: F401
    from testforge.generation import models as _generation  # noqa: F401
    from testforge.instance import models as _instance  # noqa: F401
    from testforge.jobs import models as _jobs  # noqa: F401
    from testforge.orgs import models as _orgs  # noqa: F401
    from testforge.projects import models as _projects  # noqa: F401
    from testforge.providers import models as _providers  # noqa: F401
    from testforge.pulls import models as _pulls  # noqa: F401
    from testforge.reports import models as _reports  # noqa: F401
    from testforge.runs import models as _runs  # noqa: F401
    from testforge.sources import models as _sources  # noqa: F401
    from testforge.specs import models as _specs  # noqa: F401
    from testforge.usage import models as _usage  # noqa: F401
    from testforge.users import models as _users  # noqa: F401
    from testforge.webhooks import models as _webhooks  # noqa: F401
