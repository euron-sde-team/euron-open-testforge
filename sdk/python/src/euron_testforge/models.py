"""Typed views of the API's answers. Each keeps the raw JSON in ``raw`` too."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Import:
    id: str
    status: str
    kind: str
    label: str
    languages: list[str]
    frameworks: list[str]
    units: int
    error: str | None
    raw: dict[str, Any] = field(repr=False)

    @property
    def ready(self) -> bool:
        return self.status == "ready"

    @classmethod
    def of(cls, d: dict[str, Any]) -> Import:
        return cls(
            id=str(d["id"]),
            status=str(d["status"]),
            kind=str(d["kind"]),
            label=str(d.get("label", "")),
            languages=list(d.get("languages", [])),
            frameworks=list(d.get("frameworks", [])),
            units=int((d.get("summary") or {}).get("units", 0)),
            error=d.get("error"),
            raw=d,
        )


@dataclass(frozen=True)
class Generation:
    id: str
    status: str
    accepted_count: int
    rejected_count: int
    rejections: list[dict[str, Any]]
    error: str | None
    raw: dict[str, Any] = field(repr=False)

    @classmethod
    def of(cls, d: dict[str, Any]) -> Generation:
        return cls(
            id=str(d["id"]),
            status=str(d["status"]),
            accepted_count=int(d.get("accepted_count", 0)),
            rejected_count=int(d.get("rejected_count", 0)),
            rejections=list(d.get("rejections", [])),
            error=d.get("error"),
            raw=d,
        )


@dataclass(frozen=True)
class GeneratedTest:
    id: str
    name: str
    kind: str
    status: str
    file_path: str
    description: str
    last_outcome: str | None
    raw: dict[str, Any] = field(repr=False)

    __test__ = False

    @classmethod
    def of(cls, d: dict[str, Any]) -> GeneratedTest:
        return cls(
            id=str(d["id"]),
            name=str(d["name"]),
            kind=str(d["kind"]),
            status=str(d["status"]),
            file_path=str(d["file_path"]),
            description=str(d.get("description", "")),
            last_outcome=d.get("last_outcome"),
            raw=d,
        )


@dataclass(frozen=True)
class Failure:
    test: str
    actual: str | None
    expected: str | None
    explanation: str

    @classmethod
    def of(cls, case: dict[str, Any]) -> Failure:
        f = case.get("failure") or {}
        return cls(
            test=str(case.get("name", "")),
            actual=f.get("actual"),
            expected=f.get("expected"),
            explanation=str(f.get("explanation") or case.get("message") or ""),
        )


@dataclass(frozen=True)
class Run:
    id: str
    status: str
    passed: int
    failed: int
    errors: int
    coverage_percent: float | None
    limit_exceeded: str | None
    message: str | None
    failures: list[Failure]
    raw: dict[str, Any] = field(repr=False)

    @property
    def ok(self) -> bool:
        return self.status == "passed"

    @property
    def finished(self) -> bool:
        return self.status not in ("queued", "running")

    @classmethod
    def of(cls, d: dict[str, Any]) -> Run:
        return cls(
            id=str(d["id"]),
            status=str(d["status"]),
            passed=int(d.get("passed", 0)),
            failed=int(d.get("failed", 0)),
            errors=int(d.get("errors", 0)),
            coverage_percent=d.get("coverage_percent"),
            limit_exceeded=d.get("limit_exceeded"),
            message=d.get("message"),
            failures=[
                Failure.of(c) for c in d.get("cases", []) if c.get("outcome") in ("failed", "error")
            ],
            raw=d,
        )
