"""TestForge's pytest plugin. It runs inside the sandbox, under the jail's own Python.

It records, from the one execution that ran the tests:

* every test's outcome, duration and location;
* for a failed comparison assertion, the operator and both operands as pytest saw them
  (``pytest_assertrepr_compare`` is called with the real values, before they become text),
  so the failure explanation shows actual and expected values without running the test a
  second time;
* a line per event in ``events.jsonl`` as it happens, so when the sandbox stops the run at
  a limit, the worker still knows which tests finished and which one was running.

It writes only under ``$TESTFORGE_OUT`` (``/box/.testforge``) and imports nothing outside
the standard library and pytest.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import pytest

OUT = os.environ.get("TESTFORGE_OUT", "/box/.testforge")
MAX_REPR = 600
MAX_TEXT = 4000

_compares: dict[str, dict[str, Any]] = {}
_current: list[str] = []
_tests: list[dict[str, Any]] = []
_collect_errors: list[dict[str, Any]] = []
_started = time.time()


def _repr(value: Any) -> str:
    try:
        text = repr(value)
    except Exception as exc:  # a broken __repr__ in the code under test
        text = f"<unrepresentable {type(value).__name__}: {exc}>"
    return text if len(text) <= MAX_REPR else text[: MAX_REPR - 3] + "..."


def _event(kind: str, **data: Any) -> None:
    line = json.dumps({"event": kind, "t": round(time.time() - _started, 3), **data})
    try:
        with open(os.path.join(OUT, "events.jsonl"), "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass  # the code under test removed or replaced the file; the report still lands


def pytest_configure(config: pytest.Config) -> None:
    os.makedirs(OUT, exist_ok=True)


def pytest_runtest_logstart(nodeid: str, location: tuple[str, int | None, str]) -> None:
    _current.append(nodeid)
    _event("start", nodeid=nodeid)


def pytest_assertrepr_compare(config: pytest.Config, op: str, left: Any, right: Any) -> None:
    # Called only for a failing comparison. The left operand is what the code produced in
    # the usual `assert result == expected` form; both are kept as pytest reported them.
    if _current:
        _compares[_current[-1]] = {
            "operator": op,
            "left": _repr(left),
            "right": _repr(right),
            "left_type": type(left).__name__,
            "right_type": type(right).__name__,
        }


def _failure(report: pytest.TestReport) -> dict[str, Any]:
    crash = getattr(report.longrepr, "reprcrash", None)
    message = str(crash.message) if crash is not None else str(report.longrepr)[:MAX_TEXT]
    path = str(crash.path) if crash is not None else ""
    line = int(crash.lineno) if crash is not None else None
    # When the error was raised deeper (in the code under test, or the standard library),
    # point at the line of the test itself: the last traceback entry in the test's file.
    own = report.location[0]
    entries = getattr(getattr(report.longrepr, "reprtraceback", None), "reprentries", []) or []
    for entry in reversed(entries):
        loc = getattr(entry, "reprfileloc", None)
        if loc is not None and str(loc.path).endswith(own):
            path, line = own, int(loc.lineno)
            break
    failure: dict[str, Any] = {
        "message": message[:MAX_TEXT],
        "path": path.removeprefix("/box/"),
        "line": line,
        "text": str(report.longreprtext)[-MAX_TEXT:],
    }
    compare = _compares.get(report.nodeid)
    if compare:
        failure["compare"] = compare
    return failure


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    outcome: str | None = None
    if report.when == "call":
        outcome = report.outcome  # passed, failed or skipped
    elif report.when == "setup" and report.outcome != "passed":
        outcome = "skipped" if report.skipped else "error"
    elif report.when == "teardown" and report.failed:
        outcome = "error"
    if outcome is None:
        return
    entry: dict[str, Any] = {
        "nodeid": report.nodeid,
        "file": report.location[0],
        "line": (report.location[1] or 0) + 1,
        "name": report.location[2],
        "outcome": outcome,
        "duration_ms": round(report.duration * 1000, 3),
    }
    if outcome in ("failed", "error"):
        entry["failure"] = _failure(report)
    # A teardown error after a passed call replaces the passed entry.
    if report.when == "teardown":
        _tests[:] = [t for t in _tests if t["nodeid"] != report.nodeid]
    _tests.append(entry)
    _event("result", **entry)


def pytest_runtest_logfinish(nodeid: str, location: tuple[str, int | None, str]) -> None:
    if _current and _current[-1] == nodeid:
        _current.pop()


def pytest_collectreport(report: pytest.CollectReport) -> None:
    if report.failed:
        error = {"nodeid": report.nodeid, "text": str(report.longreprtext)[-MAX_TEXT:]}
        _collect_errors.append(error)
        _event("collect_error", **error)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    data = {
        "framework": "pytest",
        "exitstatus": int(exitstatus),
        "tests": _tests,
        "collect_errors": _collect_errors,
        "duration_s": round(time.time() - _started, 3),
    }
    with open(os.path.join(OUT, "report.json"), "w", encoding="utf-8") as fh:
        json.dump(data, fh)
