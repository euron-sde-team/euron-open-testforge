from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from testforge.core.schemas import ApiModel, Email

ProjectRole = Literal["viewer", "editor", "admin"]
Scope = Literal["read", "generate", "execute", "manage"]


class ProjectCreate(ApiModel):
    # The organization it belongs to (you need the admin role there).
    org_id: uuid.UUID
    name: str = Field(min_length=1, max_length=120)
    slug: str | None = Field(None, max_length=64, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    description: str = Field("", max_length=2000)


class ProjectUpdate(ApiModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    description: str | None = Field(None, max_length=2000)
    # The GitHub repository imports and pull requests come from (owner/name or its URL).
    github_repo: str | None = Field(None, max_length=300)
    # A token for a private repository (read access to contents and pull requests). Sealed;
    # never returned. An empty string removes it.
    github_token: str | None = Field(None, max_length=400)
    # The run budget, under the server's ceilings (null keeps the server defaults).
    run_cpu_s: int | None = Field(None, ge=1, le=7200)
    run_wall_s: int | None = Field(None, ge=1, le=7200)
    run_memory_mb: int | None = Field(None, ge=64, le=65536)
    run_output_bytes: int | None = Field(None, ge=10_000, le=500_000_000)


class ProjectOut(ApiModel):
    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    slug: str
    description: str
    created_at: datetime
    role: ProjectRole = "viewer"
    github_repo: str | None = None
    has_github_token: bool = False
    current_import_id: uuid.UUID | None = None
    run_cpu_s: int | None = None
    run_wall_s: int | None = None
    run_memory_mb: int | None = None
    run_output_bytes: int | None = None
    # Accepted generated tests, and the latest finished run.
    tests: int = 0
    last_run_status: str | None = None
    coverage_percent: float | None = None


class MemberOut(ApiModel):
    user_id: uuid.UUID
    email: str
    name: str
    role: ProjectRole
    created_at: datetime


class MemberAdd(ApiModel):
    email: Email
    role: ProjectRole = "viewer"


class MemberUpdate(ApiModel):
    role: ProjectRole


def _default_scopes() -> list[Scope]:
    return ["read", "generate", "execute"]


class ApiKeyCreate(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    scopes: list[Scope] = Field(default_factory=_default_scopes, min_length=1)

    @field_validator("scopes")
    @classmethod
    def _unique(cls, v: list[str]) -> list[str]:
        return sorted(set(v))


class ApiKeyOut(ApiModel):
    id: uuid.UUID
    name: str
    prefix: str
    scopes: list[str]
    last_used_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class ApiKeyCreated(ApiKeyOut):
    key: str = Field(description="Shown once. Store it now; only a hash is kept")
