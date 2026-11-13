"""Reading a run's results: the report, or the event log when a limit stopped the run."""

from __future__ import annotations

import json

from testforge.reports.service import _cell, _csv
from testforge.runs.service import _cases, _language, _source_line
from testforge.sandbox.protocol import RunResult
from testforge.sources.models import SourceImport


def test_cases_from_the_report_include_collection_errors() -> None:
    report = {
        "tests": [{"nodeid": "t.py::a", "file": "t.py", "name": "a", "outcome": "passed"}],
        "collect_errors": [{"nodeid": "bad_test.py", "text": "SyntaxError"}],
    }
    cases = _cases(RunResult(exit_code=1, report=json.dumps(report)))
    assert [c["outcome"] for c in cases] == ["passed", "error"]
    assert cases[1]["name"] == "collecting bad_test.py"


def test_a_run_stopped_at_a_limit_keeps_finished_tests_and_names_the_running_one() -> None:
    events = (
        "\n".join(
            json.dumps(e)
            for e in (
                {"event": "start", "nodeid": "t.py::a"},
                {
                    "event": "result",
                    "nodeid": "t.py::a",
                    "file": "t.py",
                    "name": "a",
                    "outcome": "passed",
                    "t": 0.1,
                },
                {"event": "start", "nodeid": "t.py::slow"},
            )
        )
        + "\nnot json\n"
    )
    result = RunResult(
        exit_code=None, signal=9, events=events, limit_exceeded="wall_clock", limit_detail="stopped"
    )
    cases = _cases(result)
    assert cases[0]["outcome"] == "passed"
    assert cases[1]["nodeid"] == "t.py::slow" and cases[1]["outcome"] == "error"
    assert cases[1]["failure"]["limit"] == "wall_clock"


def test_language_choice() -> None:
    imp = SourceImport(languages=["python", "typescript"])
    assert _language(imp, None) == "python"
    assert _language(imp, "javascript") == "typescript"
    assert _language(SourceImport(languages=["javascript"]), None) == "javascript"


def test_source_line() -> None:
    assert _source_line("a\nb\nc", 2) == "b"
    assert _source_line("a", 5) is None and _source_line(None, 1) is None


def test_csv_cells_never_become_formulas() -> None:
    assert _cell("=HYPERLINK(1)") == "'=HYPERLINK(1)" and _cell(None) == "" and _cell(3) == "3"
    assert _csv([["a", "+1"]]).decode().strip() == "a,'+1"
