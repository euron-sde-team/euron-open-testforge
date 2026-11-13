"""Coverage reports read from the tools' own formats (never estimated)."""

from __future__ import annotations

import json

import pytest

from testforge.coverage.parse import CoverageError, parse, unit_percent

COVERAGE_PY = {
    "meta": {"version": "7.10"},
    "files": {
        "app/pricing.py": {
            "executed_lines": [1, 2, 3, 5],
            "missing_lines": [6, 7, 9],
            "summary": {"num_branches": 4, "covered_branches": 3},
        },
        "/box/app/cart.py": {"executed_lines": [], "missing_lines": [1, 2], "summary": {}},
    },
    "totals": {"percent_covered": 44.4},
}

ISTANBUL = {
    "/box/src/money.ts": {
        "path": "/box/src/money.ts",
        "statementMap": {
            "0": {"start": {"line": 3, "column": 2}, "end": {"line": 3, "column": 9}},
            "1": {"start": {"line": 4, "column": 2}, "end": {"line": 4, "column": 9}},
            "2": {"start": {"line": 4, "column": 12}, "end": {"line": 4, "column": 20}},
            "3": {"start": {"line": 8, "column": 2}, "end": {"line": 8, "column": 9}},
        },
        "s": {"0": 2, "1": 0, "2": 1, "3": 0},
        "b": {"0": [1, 0], "1": [3, 2]},
    }
}


def test_coverage_py() -> None:
    cov = parse("coverage.py", json.dumps(COVERAGE_PY))
    assert cov.tool == "coverage.py"
    assert [f.path for f in cov.files] == ["app/cart.py", "app/pricing.py"]
    assert cov.lines_total == 9 and cov.lines_covered == 4
    assert cov.line_percent == pytest.approx(44.44)
    assert cov.branch_percent == 75.0
    pricing = cov.by_path()["app/pricing.py"]
    assert pricing.missing_ranges() == [[6, 7], [9, 9]]
    assert pricing.as_dict()["percent"] == pytest.approx(57.14)
    assert unit_percent(pricing, 5, 7) == pytest.approx(33.33)
    assert unit_percent(pricing, 20, 30) is None
    # The def line ran on import; the body (6, 7) never did.
    assert unit_percent(pricing, 5, 7, [6, 7]) == 0.0
    assert unit_percent(None, 1, 2) is None


def test_istanbul_counts_a_line_covered_when_any_statement_on_it_ran() -> None:
    cov = parse("istanbul", json.dumps(ISTANBUL))
    money = cov.by_path()["src/money.ts"]
    assert money.statements == {3, 4, 8}
    assert money.covered == {3, 4}
    assert cov.branches_total == 4 and cov.branches_covered == 3
    assert cov.line_percent == pytest.approx(66.67)


@pytest.mark.parametrize(
    ("tool", "text"),
    [
        ("coverage.py", "not json"),
        ("coverage.py", "[]"),
        ("coverage.py", "{}"),
        ("istanbul", '{"a": 1}'),
        ("lcov", "{}"),
    ],
)
def test_unknown_or_broken_reports_are_refused(tool: str, text: str) -> None:
    with pytest.raises(CoverageError):
        parse(tool, text)


def test_an_empty_report_is_zero_not_a_guess() -> None:
    cov = parse("coverage.py", json.dumps({"files": {}}))
    assert cov.line_percent == 0.0 and cov.branch_percent is None
