"""Imported source code and what static analysis found in it.

An import is one immutable snapshot of a project's source: a GitHub repository at one
commit, or one uploaded ZIP. The snapshot itself lives in object storage (rows keep only
its key); analysis fills ``code_units`` (functions, methods, classes and routes) and the
import's summary. Nothing in an import is ever executed outside the sandbox.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from testforge.core.db import Base, TimestampMixin, new_id

IMPORT_KINDS = ("zip", "github", "pull_request")
IMPORT_STATUSES = ("pending", "analyzing", "ready", "failed")
UNIT_KINDS = ("function", "method", "class", "route")
LANGUAGES = ("python", "javascript", "typescript")


class SourceImport(TimestampMixin, Base):
    __tablename__ = "source_imports"
    __table_args__ = (
        CheckConstraint("kind IN ('zip', 'github', 'pull_request')", name="ck_imports_kind"),
        CheckConstraint(
            "status IN ('pending', 'analyzing', 'ready', 'failed')", name="ck_imports_status"
        ),
        Index("ix_source_imports_project_created", "project_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    # Where it came from: the uploaded file name, or owner/repo at a ref and commit.
    label: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    repo: Mapped[str | None] = mapped_column(String(200))
    ref: Mapped[str | None] = mapped_column(String(200))
    commit_sha: Mapped[str | None] = mapped_column(String(64))
    # The raw upload (kept until unpacked) and the normalized snapshot every run unpacks.
    upload_key: Mapped[str | None] = mapped_column(String(300))
    snapshot_key: Mapped[str | None] = mapped_column(String(300))
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    file_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Detected languages (python, javascript, typescript), frameworks and test frameworks.
    languages: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    frameworks: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    test_frameworks: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    # Counts, dependencies, existing test files, skipped files, the app entry for API tests.
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    analysis_ms: Mapped[int | None] = mapped_column(Integer)
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class CodeUnit(Base):
    """A function, method, class or route found by static analysis of one import."""

    __tablename__ = "code_units"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('function', 'method', 'class', 'route')", name="ck_code_units_kind"
        ),
        Index("ix_code_units_import_file", "import_id", "file"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    import_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_imports.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    language: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # module.Class.method, or "GET /items/{id}" for a route.
    qualname: Mapped[str] = mapped_column(String(400), nullable=False)
    file: Mapped[str] = mapped_column(String(500), nullable=False)
    # The importable module (Python) or the path without extension (JavaScript).
    module: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    signature: Mapped[str] = mapped_column(Text, nullable=False, default="")
    docstring: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # The unit's own source (capped), quoted into prompts.
    source: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Parameters, return type, documented examples, raised errors and their conditions,
    # the route's method and path, the class a method belongs to.
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    exported: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_async: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Statements a test could execute (static count), used for coverage per unit.
    statement_lines: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Whether any test file of the project names this unit (the static untested check).
    referenced_by_tests: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # From the latest run with coverage of this import: covered lines in the unit's range.
    covered_percent: Mapped[float | None] = mapped_column(Float)
