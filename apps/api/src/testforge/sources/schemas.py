from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from testforge.core.schemas import ApiModel


class GitHubImport(ApiModel):
    # owner/name or https://github.com/owner/name; empty uses the project's repository.
    repo: str | None = Field(None, max_length=300)
    # A branch, tag or commit; empty uses the default branch.
    ref: str | None = Field(None, max_length=200, pattern=r"^[A-Za-z0-9._/-]+$")


class ImportOut(ApiModel):
    id: uuid.UUID
    kind: Literal["zip", "github", "pull_request"]
    status: Literal["pending", "analyzing", "ready", "failed"]
    label: str
    repo: str | None
    ref: str | None
    commit_sha: str | None
    size_bytes: int
    file_count: int
    languages: list[str]
    frameworks: list[str]
    test_frameworks: list[str]
    summary: dict[str, Any]
    error: str | None
    analysis_ms: int | None
    analyzed_at: datetime | None
    created_at: datetime


class UnitOut(ApiModel):
    id: uuid.UUID
    kind: Literal["function", "method", "class", "route"]
    language: str
    name: str
    qualname: str
    file: str
    module: str
    start_line: int
    end_line: int
    signature: str
    docstring: str
    exported: bool
    is_async: bool
    statement_lines: int
    referenced_by_tests: bool
    covered_percent: float | None
    details: dict[str, Any]


class UnitDetail(UnitOut):
    source: str


class FileOut(ApiModel):
    path: str
    bytes: int
    language: str | None


class FileContent(ApiModel):
    path: str
    content: str
    language: str | None
    units: list[UnitOut]
    # Lines a coverage report saw run and lines it saw not run (latest run with coverage).
    covered_lines: list[int] = Field(default_factory=list)
    missing_lines: list[int] = Field(default_factory=list)


class AnalysisOut(ApiModel):
    """The project's current source analysis at a glance."""

    import_: ImportOut | None = Field(None, alias="import")
    units: int = 0
    by_kind: dict[str, int] = Field(default_factory=dict)
    untested: int = 0
    untested_units: list[UnitOut] = Field(default_factory=list)
