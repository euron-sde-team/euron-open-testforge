"""Instance-wide settings: one row, created with safe defaults on first read."""

from __future__ import annotations

from sqlalchemy import Boolean, CheckConstraint, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from testforge.core.db import Base, TimestampMixin

SINGLETON_ID = 1


class InstanceSettings(TimestampMixin, Base):
    """Settings of this TestForge server. Exactly one row (id 1).

    Tenants (organizations) hold everything else; these only say how the server presents
    itself and whether people may create their own account (and with it an organization).
    """

    __tablename__ = "instance_settings"
    __table_args__ = (CheckConstraint("id = 1", name="ck_instance_settings_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=SINGLETON_ID)
    site_name: Mapped[str] = mapped_column(String(80), nullable=False, default="TestForge")
    # Off by default: an admin invites people; open sign-up suits a sandbox instance.
    allow_signup: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
