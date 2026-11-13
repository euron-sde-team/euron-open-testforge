from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from testforge.core.schemas import ApiModel

RunStatus = Literal["queued", "running", "passed", "failed", "error", "limit_exceeded"]


class RunCreate(ApiModel):
    # generated: the chosen (or accepted) generated tests; project: the project's own test
    # suite; all: both together.
    kind: Literal["generated", "project", "all"] = "generated"
    test_ids: list[uuid.UUID] | None = Field(None, max_length=1000)
    import_id: uuid.UUID | None = None
    language: Literal["python", "javascript", "typescript"] | None = None


class RunOut(ApiModel):
    id: uuid.UUID
    import_id: uuid.UUID
    kind: Literal["generated", "project", "all"]
    language: str
    framework: str
    status: RunStatus
    test_ids: list[str]
    limits: dict[str, int]
    limit_exceeded: Literal["cpu", "memory", "wall_clock", "output", "processes"] | None
    exit_code: int | None
    signal: int | None
    cpu_ms: int | None
    wall_ms: int | None
    memory_kb: int | None
    output_bytes: int | None
    passed: int
    failed: int
    errors: int
    skipped: int
    coverage_percent: float | None
    message: str | None
    trigger: str
    actor: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class CaseOut(ApiModel):
    id: uuid.UUID
    generated_test_id: uuid.UUID | None
    nodeid: str
    file: str
    name: str
    outcome: Literal["passed", "failed", "error", "skipped"]
    duration_ms: float
    message: str
    failure: dict[str, Any] | None


class RunDetail(RunOut):
    stdout_tail: str
    stderr_tail: str
    cases: list[CaseOut] = Field(default_factory=list)
