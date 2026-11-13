"""Projects group imported source, generated tests, runs, coverage and model providers
inside an organization; members hold a role in each."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from testforge.core.db import Base, TimestampMixin, new_id

PROJECT_ROLES = ("viewer", "editor", "admin")


class Project(TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("org_id", "slug", name="uq_projects_org_slug"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # The GitHub repository (owner/name) this project imports from, and an optional token
    # for private repositories (sealed, never returned).
    github_repo: Mapped[str | None] = mapped_column(String(200))
    github_token_sealed: Mapped[bytes | None] = mapped_column(LargeBinary)
    # The secret GitHub signs webhook deliveries with (sealed; shown once when rotated).
    github_webhook_secret_sealed: Mapped[bytes | None] = mapped_column(LargeBinary)
    # The run budget for this project, under the instance ceilings (null: the defaults).
    run_cpu_s: Mapped[int | None] = mapped_column(Integer)
    run_wall_s: Mapped[int | None] = mapped_column(Integer)
    run_memory_mb: Mapped[int | None] = mapped_column(Integer)
    run_output_bytes: Mapped[int | None] = mapped_column(Integer)
    # The import that generation and runs use by default (the latest ready one).
    current_import_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class ProjectMember(TimestampMixin, Base):
    __tablename__ = "project_members"
    __table_args__ = (
        CheckConstraint("role IN ('viewer', 'editor', 'admin')", name="ck_member_role"),
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)


class ApiKey(TimestampMixin, Base):
    """A project's key for other applications and CI. Only a peppered hash is stored."""

    __tablename__ = "api_keys"
    __table_args__ = (UniqueConstraint("prefix", name="uq_api_keys_prefix"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    secret_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
