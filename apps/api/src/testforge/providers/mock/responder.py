"""What the deterministic mock model answers.

It reads the JSON request TestForge puts in every prompt and writes tests only from facts
in it: documented examples become equality assertions, simple raise conditions become
boundary and negative tests, documented operations become API tests. When a unit offers
nothing to ground a test in, it writes what a weak model writes, a call with no assertion,
and TestForge's assertion check refuses it (so the guard is visible in the demo). For a
failure explanation it restates the captured values in plain words.
"""

from __future__ import annotations

import json
from typing import Any

from testforge.generation import templates
from testforge.generation.prompt import read_request


def _unit_tests(req: dict[str, Any]) -> list[templates.Draft]:
    kinds = set(req.get("kinds") or ["unit"])
    js = req.get("framework") == "vitest"
    drafts: list[templates.Draft] = []
    for unit in req.get("units", []):
        mine: list[templates.Draft] = []
        if unit["kind"] in ("function", "method", "class"):
            if "unit" in kinds:
                mine += (
                    templates.js_example_tests(unit) if js else templates.python_example_tests(unit)
                )
            if kinds & {"edge", "negative"} and unit["kind"] != "class":
                raised = (
                    templates.js_raise_tests(unit) if js else templates.python_raise_tests(unit)
                )
                mine += [d for d in raised if d.kind in kinds or js]
        if not mine and "unit" in kinds and unit["kind"] != "route":
            mine.append(templates.js_smoke_test(unit) if js else templates.python_smoke_test(unit))
        drafts += mine
    return drafts


def _api_tests(req: dict[str, Any]) -> list[templates.Draft]:
    app = req.get("app") or {}
    doc = req.get("document") or {}
    drafts: list[templates.Draft] = []
    for op in req.get("operations", []):
        drafts.append(templates.api_test(op, app, doc))
        negative = templates.api_negative_test(op, app, doc)
        if negative is not None:
            drafts.append(negative)
    return drafts


def explain(failure: dict[str, Any]) -> str:
    compare = failure.get("compare") or {}
    test = failure.get("test", "The test")
    if compare:
        return (
            f"{test} failed because the code returned {compare.get('left')} where the test "
            f"expected {compare.get('right')} (operator {compare.get('operator', '==')}). "
            "Compare the expected value with the documentation of the code under test: if "
            "the documentation is right, the code has a bug; if the code is right, update "
            "the documentation and the test."
        )
    message = failure.get("message") or "an error"
    return (
        f"{test} failed with {message}. Read the line the failure points at and the input "
        "the test passes there."
    )


def respond(system: str, user: str) -> str:
    req = read_request(user) or read_request(system)
    if req is None:
        return "TestForge mock model: send a TestForge request to get tests."
    mode = req.get("mode")
    if mode == "explain":
        return explain(req.get("failure") or {})
    drafts = _api_tests(req) if mode == "api" else _unit_tests(req)
    return json.dumps(
        {
            "tests": [
                {
                    "name": d.name,
                    "target": d.target,
                    "kind": d.kind,
                    "code": d.code,
                    "description": d.description,
                }
                for d in drafts
            ]
        }
    )
