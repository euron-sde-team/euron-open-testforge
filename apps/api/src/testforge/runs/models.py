"""Test runs: one sandboxed execution of a project's tests, and each test case's result.

Every run, generated tests or the project's own suite, executes in the sandbox service
under a CPU, memory, output and wall clock budget. The run keeps the sandbox's
measurements and, when a limit stopped it, which one.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
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

from testforge.core.db import Base, new_id

RUN_KINDS = ("generated", "project", "all")
RUN_STATUSES = ("queued", "running", "passed", "failed", "error", "limit_exceeded")
FINAL_RUN_STATUSES = ("passed", "failed", "error", "limit_exceeded")
LIMITS = ("cpu", "memory", "wall_clock", "output", "processes")
OUTCOMES = ("passed", "failed", "error", "skipped")


class TestRun(Base):
    __tablename__ = "test_runs"
    __table_args__ = (
        CheckConstraint("kind IN ('generated', 'project', 'all')", name="ck_runs_kind"),
        CheckConstraint(
            "status IN ('queued', 'running', 'passed', 'failed', 'error', 'limit_exceeded')",
            name="ck_runs_status",
        ),
        CheckConstraint(
            "limit_exceeded IS NULL OR limit_exceeded IN "
            "('cpu', 'memory', 'wall_clock', 'output', 'processes')",
            name="ck_runs_limit",
        ),
        Index("ix_test_runs_project_created", "project_id", "created_at"),
    )
    __test__ = False  # not a pytest class, whatever its name says

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    import_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_imports.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    language: Mapped[str] = mapped_column(String(16), nullable=False)
    framework: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    # Generated tests included (kind generated or all).
    test_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    # The budget this run had: {"cpu_s", "wall_s", "memory_mb", "output_bytes"}.
    limits: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    limit_exceeded: Mapped[str | None] = mapped_column(String(16))
    exit_code: Mapped[int | None] = mapped_column(Integer)
    signal: Mapped[int | None] = mapped_column(Integer)
    cpu_ms: Mapped[int | None] = mapped_column(Integer)
    wall_ms: Mapped[int | None] = mapped_column(Integer)
    memory_kb: Mapped[int | None] = mapped_column(BigInteger)
    output_bytes: Mapped[int | None] = mapped_column(BigInteger)
    passed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Line coverage of the project's source in this run (null when not measured).
    coverage_percent: Mapped[float | None] = mapped_column(Float)
    stdout_tail: Mapped[str] = mapped_column(Text, nullable=False, default="")
    stderr_tail: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # A plain-language reason when the run is an error or crossed a limit.
    message: Mapped[str | None] = mapped_column(Text)
    trigger: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    actor: Mapped[str] = mapped_column(String(320), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TestCaseResult(Base):
    """One test case of a run: its outcome and, when it failed, the failure as captured in
    that same execution (the assertion, the actual and expected values, the location)."""

    __tablename__ = "test_case_results"
    __table_args__ = (
        CheckConstraint(
            "outcome IN ('passed', 'failed', 'error', 'skipped')", name="ck_cases_outcome"
        ),
    )
    __test__ = False

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("test_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    generated_test_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("generated_tests.id", ondelete="SET NULL"), index=True
    )
    nodeid: Mapped[str] = mapped_column(String(600), nullable=False)
    file: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    duration_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # {"kind", "operator", "actual", "expected", "expression", "line", "explanation"}
    failure: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
