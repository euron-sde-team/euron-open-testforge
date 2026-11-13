"""Organizations are the tenants: every project, import, generated test and run belongs to one."""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from testforge.core.db import Base, TimestampMixin, new_id

ORG_ROLES = ("member", "admin", "owner")


class Organization(TimestampMixin, Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class OrgMember(TimestampMixin, Base):
    """A person in an organization. Owners and admins act as owners of every project in
    it; members see only the projects they are added to."""

    __tablename__ = "org_members"
    __table_args__ = (
        CheckConstraint("role IN ('member', 'admin', 'owner')", name="ck_org_member_role"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
