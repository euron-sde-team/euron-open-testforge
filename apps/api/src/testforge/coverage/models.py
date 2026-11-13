"""Coverage measured in a run, read from the coverage tool's own report (coverage.py for
Python, Istanbul for JavaScript and TypeScript), never estimated."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from testforge.core.db import Base, new_id


class CoverageReport(Base):
    __tablename__ = "coverage_reports"
    __table_args__ = (Index("ix_coverage_project_created", "project_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("test_runs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    import_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_imports.id", ondelete="CASCADE"), nullable=False
    )
    tool: Mapped[str] = mapped_column(String(32), nullable=False)
    lines_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lines_covered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    line_percent: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    branches_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    branches_covered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    branch_percent: Mapped[float | None] = mapped_column(Float)
    # [{"path", "lines_total", "lines_covered", "percent", "missing": [[start, end], ...]}]
    files: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
