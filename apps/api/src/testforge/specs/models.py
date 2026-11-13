"""Imported OpenAPI documents, the source of API test generation."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from testforge.core.db import Base, TimestampMixin, new_id


class ApiSpec(TimestampMixin, Base):
    """One OpenAPI 3 document, normalized into the operations API tests are written for.

    The document is kept (capped by MAX_SPEC_BYTES) so operations can be re-derived; the
    operations list is what prompts and the coverage check read.
    """

    __tablename__ = "api_specs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    document: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # [{"id", "method", "path", "summary", "parameters", "request_body", "responses"}]
    operations: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    operation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
