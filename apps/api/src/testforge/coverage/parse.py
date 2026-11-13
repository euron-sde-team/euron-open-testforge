"""Read the coverage tools' own reports into one shape: totals and per-file line coverage.

* coverage.py: the JSON report (``coverage json``, written by pytest-cov), with each file's
  ``executed_lines``, ``missing_lines`` and summary.
* Istanbul: ``coverage-final.json`` (Vitest's istanbul provider), with each file's
  ``statementMap`` and hit counts ``s``, and branch hit counts ``b``. A line is covered when
  a statement starting on it ran.

Paths are made relative to the workspace (``/box``). Nothing is estimated: a line counts
only when the tool says it is a statement, and covered only when the tool saw it run.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

ROOT = "/box/"


class CoverageError(Exception):
    """The report is not one of the supported formats."""


@dataclass
class FileCoverage:
    path: str
    covered: set[int]
    statements: set[int]

    @property
    def percent(self) -> float:
        return (
            round(100.0 * len(self.covered) / len(self.statements), 2) if self.statements else 100.0
        )

    def missing_ranges(self) -> list[list[int]]:
        missing = sorted(self.statements - self.covered)
        out: list[list[int]] = []
        for n in missing:
            if out and n == out[-1][1] + 1:
                out[-1][1] = n
            else:
                out.append([n, n])
        return out

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "lines_total": len(self.statements),
            "lines_covered": len(self.covered),
            "percent": self.percent,
            "missing": self.missing_ranges()[:200],
        }


@dataclass
class Coverage:
    tool: str
    files: list[FileCoverage] = field(default_factory=list)
    branches_total: int = 0
    branches_covered: int = 0

    @property
    def lines_total(self) -> int:
        return sum(len(f.statements) for f in self.files)

    @property
    def lines_covered(self) -> int:
        return sum(len(f.covered) for f in self.files)

    @property
    def line_percent(self) -> float:
        total = self.lines_total
        return round(100.0 * self.lines_covered / total, 2) if total else 0.0

    @property
    def branch_percent(self) -> float | None:
        if not self.branches_total:
            return None
        return round(100.0 * self.branches_covered / self.branches_total, 2)

    def by_path(self) -> dict[str, FileCoverage]:
        return {f.path: f for f in self.files}


def _rel(path: str) -> str:
    return path[len(ROOT) :] if path.startswith(ROOT) else path.lstrip("./")


def parse_coverage_py(data: dict[str, Any]) -> Coverage:
    files = data.get("files")
    if not isinstance(files, dict):
        raise CoverageError("not a coverage.py JSON report (no files)")
    cov = Coverage(tool="coverage.py")
    for path, f in files.items():
        executed = {int(n) for n in f.get("executed_lines", [])}
        missing = {int(n) for n in f.get("missing_lines", [])}
        cov.files.append(FileCoverage(_rel(path), executed, executed | missing))
        summary = f.get("summary", {})
        cov.branches_total += int(summary.get("num_branches", 0) or 0)
        cov.branches_covered += int(summary.get("covered_branches", 0) or 0)
    cov.files.sort(key=lambda x: x.path)
    return cov


def parse_istanbul(data: dict[str, Any]) -> Coverage:
    cov = Coverage(tool="istanbul")
    for key, f in data.items():
        if not isinstance(f, dict) or "statementMap" not in f:
            raise CoverageError("not an Istanbul coverage-final.json report")
        statements: set[int] = set()
        covered: set[int] = set()
        hits = f.get("s", {})
        for sid, loc in f["statementMap"].items():
            line = int(loc["start"]["line"])
            statements.add(line)
            if int(hits.get(sid, 0)) > 0:
                covered.add(line)
        for counts in f.get("b", {}).values():
            cov.branches_total += len(counts)
            cov.branches_covered += sum(1 for c in counts if int(c) > 0)
        cov.files.append(FileCoverage(_rel(str(f.get("path") or key)), covered, statements))
    cov.files.sort(key=lambda x: x.path)
    return cov


def parse(tool: str, text: str) -> Coverage:
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise CoverageError("the coverage report is not JSON") from exc
    if not isinstance(data, dict):
        raise CoverageError("the coverage report is not an object")
    if tool == "coverage.py":
        return parse_coverage_py(data)
    if tool == "istanbul":
        return parse_istanbul(data)
    raise CoverageError(f"unknown coverage tool {tool!r}")


def unit_percent(
    fc: FileCoverage | None, start: int, end: int, body: list[int] | None = None
) -> float | None:
    """Covered share of a unit's statements, or None when the file was not measured or the
    unit has no statement the tool counts. ``body`` (the unit's own statement lines, from
    analysis) leaves out the ``def`` or ``class`` line, which runs on import whether or not
    any test calls the unit; without it, every statement in [start, end] counts."""
    if fc is None:
        return None
    lines = set(body) if body else set(range(start, end + 1))
    stmts = {n for n in fc.statements if start <= n <= end and n in lines}
    if not stmts:
        return None
    return round(100.0 * len(stmts & fc.covered) / len(stmts), 2)
