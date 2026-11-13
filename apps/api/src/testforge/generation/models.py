"""Generations (one request to write tests) and the tests they produced.

A model's output is parsed and every test goes through the assertion check before it is
stored here: a test with no meaningful, reachable assertion is never stored as a test and
never shown; only its name and the reason are kept on the generation, so the dashboard can
say how many were refused and why.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from testforge.core.db import Base, TimestampMixin, new_id

TEST_KINDS = ("unit", "edge", "negative", "api")
GENERATION_STATUSES = ("queued", "running", "done", "failed")
TEST_STATUSES = ("proposed", "accepted", "discarded")


class Generation(TimestampMixin, Base):
    __tablename__ = "generations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'done', 'failed')", name="ck_generations_status"
        ),
        Index("ix_generations_project_created", "project_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    import_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_imports.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    # What was asked for: unit, edge and negative tests for code units, or API tests.
    kinds: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    unit_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    spec_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("api_specs.id", ondelete="SET NULL")
    )
    pull_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pull_request_imports.id", ondelete="SET NULL")
    )
    # Free text added to the prompt ("focus on rounding").
    instructions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    provider_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("model_providers.id", ondelete="SET NULL")
    )
    provider_kind: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    model: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    accepted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # [{"name", "reason", "code"}] for every test the assertion check refused.
    rejections: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    # API generation: which documented operations got at least one test.
    operations_covered: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    model_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error: Mapped[str | None] = mapped_column(Text)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    actor: Mapped[str] = mapped_column(String(320), nullable=False, default="")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GeneratedTest(TimestampMixin, Base):
    """One generated test file: its code, what it asserts, and what it checks in words."""

    __tablename__ = "generated_tests"
    __table_args__ = (
        CheckConstraint("kind IN ('unit', 'edge', 'negative', 'api')", name="ck_tests_kind"),
        CheckConstraint("status IN ('proposed', 'accepted', 'discarded')", name="ck_tests_status"),
        Index("ix_generated_tests_project_status", "project_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    import_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_imports.id", ondelete="CASCADE"), nullable=False
    )
    generation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("generations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    unit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("code_units.id", ondelete="SET NULL")
    )
    # The documented operation an API test covers ("GET /products/{id}").
    operation: Mapped[str | None] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    language: Mapped[str] = mapped_column(String(16), nullable=False)
    framework: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Where the file is written in a run's workspace.
    file_path: Mapped[str] = mapped_column(String(300), nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    # Plain-language documentation of what the test checks.
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # The assertions the check found, per test function: [{"test", "line", "text"}].
    assertions: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="proposed")
    # The outcome of the latest run that included this test.
    last_outcome: Mapped[str | None] = mapped_column(String(16))
    last_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
