from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from testforge.core.schemas import ApiModel


class CoverageOut(ApiModel):
    run_id: uuid.UUID
    import_id: uuid.UUID
    tool: str
    lines_total: int
    lines_covered: int
    line_percent: float
    branches_total: int
    branches_covered: int
    branch_percent: float | None
    files: list[dict[str, Any]]
    created_at: datetime


class TrendPoint(ApiModel):
    run_id: uuid.UUID
    line_percent: float
    branch_percent: float | None
    created_at: datetime


class ProjectCoverage(ApiModel):
    latest: CoverageOut | None
    trend: list[TrendPoint]
