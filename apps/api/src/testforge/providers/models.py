"""Model providers: a key for one provider family and the model TestForge asks for tests."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from testforge.core.db import Base, TimestampMixin, new_id

PROVIDER_KINDS = ("openai", "anthropic", "gemini", "ollama", "openai_compatible", "mock")


class ModelProvider(TimestampMixin, Base):
    """One provider with the project's own key (sealed, never returned).

    Exactly one enabled provider per project may be the default: generations use it unless
    they name another. The ``mock`` kind is TestForge's built-in deterministic model, so a
    project works with no external provider at all.
    """

    __tablename__ = "model_providers"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_model_providers_name"),
        CheckConstraint(
            "kind IN ('openai', 'anthropic', 'gemini', 'ollama', 'openai_compatible', 'mock')",
            name="ck_model_providers_kind",
        ),
        Index(
            "uq_model_providers_default",
            "project_id",
            unique=True,
            postgresql_where=text("is_default"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    # The model asked for tests and failure explanations, e.g. gpt-4.1-mini.
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    api_key_sealed: Mapped[bytes | None] = mapped_column(LargeBinary)
    # Extra headers as sealed JSON (a gateway's tenant or budget headers may be secrets).
    headers_sealed: Mapped[bytes | None] = mapped_column(LargeBinary)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    timeout_s: Mapped[float] = mapped_column(Float, nullable=False, default=60.0)
    last_test_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_test_ok: Mapped[bool | None] = mapped_column(Boolean)
    last_test_message: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
