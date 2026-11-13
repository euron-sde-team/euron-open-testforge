from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from testforge.core.schemas import ApiModel
from testforge.sources.schemas import UnitOut


class PullCreate(ApiModel):
    number: int = Field(ge=1)
    # owner/name; empty uses the project's repository.
    repo: str | None = Field(None, max_length=300)


class PullOut(ApiModel):
    id: uuid.UUID
    repo: str
    number: int
    title: str
    author: str
    base_ref: str
    base_sha: str
    head_ref: str
    head_sha: str
    status: Literal["pending", "analyzing", "ready", "failed"]
    import_id: uuid.UUID | None
    changed_files: list[dict[str, Any]]
    scoped_unit_ids: list[str]
    source: str
    error: str | None
    created_at: datetime


class PullDetail(PullOut):
    scoped_units: list[UnitOut] = Field(default_factory=list)
