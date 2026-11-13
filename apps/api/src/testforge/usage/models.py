"""Daily usage rollups: one row per project, day and model, incremented as tests are
generated and runs finish, so the usage report never scans raw history."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import BigInteger, Date, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from testforge.core.db import Base


class UsageDaily(Base):
    __tablename__ = "usage_daily"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    # "" for work with no model involved (runs).
    model: Mapped[str] = mapped_column(String(260), primary_key=True, default="")
    generations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tests_accepted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tests_rejected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    runs_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sandbox_ms: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    input_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
