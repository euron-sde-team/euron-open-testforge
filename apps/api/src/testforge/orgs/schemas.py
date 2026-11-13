"""Request and response models for organizations and their members."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from testforge.core.schemas import ApiModel, Email

OrgRole = Literal["member", "admin", "owner"]


class OrgOut(ApiModel):
    id: uuid.UUID
    name: str
    slug: str
    created_at: datetime
    # The caller's role ("owner" for instance admins who are not members).
    role: OrgRole = "member"
    projects: int = 0
    members: int = 0


class OrgCreate(ApiModel):
    name: str = Field(min_length=1, max_length=120)


class OrgUpdate(ApiModel):
    name: str | None = Field(None, min_length=1, max_length=120)


class OrgMemberOut(ApiModel):
    user_id: uuid.UUID
    email: str
    name: str
    role: OrgRole
    created_at: datetime


class OrgMemberAdd(ApiModel):
    email: Email
    role: OrgRole = "member"
    # Creates the account when no account has this email (a temporary password the person
    # changes after signing in). Without it, the account must exist.
    name: str | None = Field(None, min_length=1, max_length=200)
    password: str | None = Field(None, min_length=1, max_length=256)


class OrgMemberUpdate(ApiModel):
    role: OrgRole
