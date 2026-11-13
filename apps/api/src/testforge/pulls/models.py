"""Imported GitHub pull requests: the changed files between base and head, and the code
units those changes touch."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from testforge.core.db import Base, TimestampMixin, new_id


class PullRequestImport(TimestampMixin, Base):
    __tablename__ = "pull_request_imports"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'analyzing', 'ready', 'failed')", name="ck_pulls_status"
        ),
        UniqueConstraint("project_id", "repo", "number", "head_sha", name="uq_pulls_head"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    repo: Mapped[str] = mapped_column(String(200), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    author: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    base_ref: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    base_sha: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    head_ref: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    head_sha: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    # The import of the head commit (analyzed like any other import).
    import_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_imports.id", ondelete="SET NULL")
    )
    # [{"path", "status", "additions", "deletions", "changed_lines": [[start, end], ...]}]
    changed_files: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    # Code units of the head import whose lines the diff touches (filled after analysis).
    scoped_unit_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    # How it arrived: by hand (API, dashboard, SDK) or from the GitHub webhook.
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")
    error: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
