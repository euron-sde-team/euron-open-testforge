from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from testforge.core.schemas import ApiModel


class SpecCreate(ApiModel):
    # The OpenAPI 3 document, as JSON or YAML text.
    document: str = Field(min_length=10, max_length=5_000_000)


class OperationOut(ApiModel):
    key: str
    operation_id: str
    method: str
    path: str
    summary: str
    parameters: list[dict[str, Any]]
    request_body: dict[str, Any] | None
    responses: dict[str, Any]


class SpecOut(ApiModel):
    id: uuid.UUID
    title: str
    version: str
    operation_count: int
    operations: list[OperationOut]
    created_at: datetime
