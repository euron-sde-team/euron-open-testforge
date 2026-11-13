from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from testforge.core.schemas import ApiModel

TestKind = Literal["unit", "edge", "negative", "api"]


def _default_kinds() -> list[TestKind]:
    return ["unit", "edge", "negative"]


class GenerateRequest(ApiModel):
    # unit: documented behaviour; edge: boundary values; negative: invalid input; api: one
    # test per OpenAPI operation (needs spec_id).
    kinds: list[TestKind] = Field(default_factory=_default_kinds, min_length=1)
    import_id: uuid.UUID | None = None
    # The units to write tests for; empty: the import's untested units.
    unit_ids: list[uuid.UUID] | None = Field(None, max_length=500)
    # Scope to the units a pull request's changes touch.
    pull_id: uuid.UUID | None = None
    spec_id: uuid.UUID | None = None
    provider_id: uuid.UUID | None = None
    instructions: str = Field("", max_length=2000)


class Rejection(ApiModel):
    name: str
    code: str
    reason: str


class GenerationOut(ApiModel):
    id: uuid.UUID
    status: Literal["queued", "running", "done", "failed"]
    import_id: uuid.UUID
    kinds: list[str]
    unit_ids: list[str]
    spec_id: uuid.UUID | None
    pull_id: uuid.UUID | None
    provider_kind: str
    model: str
    accepted_count: int
    rejected_count: int
    rejections: list[Rejection]
    operations_covered: list[str]
    input_tokens: int
    output_tokens: int
    model_ms: int
    error_code: str | None
    error: str | None
    actor: str
    created_at: datetime
    finished_at: datetime | None


class AssertionOut(ApiModel):
    test: str
    line: int
    text: str


class TestOut(ApiModel):
    id: uuid.UUID
    generation_id: uuid.UUID
    import_id: uuid.UUID
    unit_id: uuid.UUID | None
    operation: str | None
    kind: TestKind
    language: str
    framework: str
    name: str
    file_path: str
    description: str
    assertions: list[AssertionOut]
    status: Literal["proposed", "accepted", "discarded"]
    last_outcome: str | None
    last_run_id: uuid.UUID | None
    created_at: datetime

    __test__ = False


class TestDetail(TestOut):
    code: str
    unit: dict[str, Any] | None = None


class TestReview(ApiModel):
    status: Literal["accepted", "discarded", "proposed"]


class BulkReview(ApiModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    status: Literal["accepted", "discarded"]


class BulkResult(ApiModel):
    changed: int
