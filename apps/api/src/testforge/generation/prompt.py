"""Prompts for test generation, built from the analyzed source, and parsing the answer.

A prompt is schema-aware: it carries each unit's real signature, parameters and types,
docstring, documented examples, the conditions under which it raises, and its source, as
one JSON request between ``<testforge-request>`` tags. Every provider gets the same
prompt; the deterministic mock provider reads the same JSON.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

REQUEST_OPEN = "<testforge-request>"
REQUEST_CLOSE = "</testforge-request>"

SYSTEM = """You write automated tests for a developer's own code. You are given the real
source of the code under test as JSON: signatures, parameter types, docstrings, documented
examples, the exact conditions under which it raises errors, and the source text.

Rules:
- Every test must contain at least one real assertion about the code under test, grounded
  in the source or its documentation: expected values from documented examples, errors
  from the raise conditions shown, documented status codes and response shapes. Never
  write a test without an assertion, never assert a constant (assert True), never assert a
  value equals itself. Tests that break these rules are discarded before anyone sees them.
- Do not guess return values the source and documentation do not establish.
- Tests run in a sandbox with no network and no installed packages beyond the test
  framework (and, for Python, fastapi, httpx, flask, pydantic, requests). Use only the
  standard library, the framework and the project's own modules.
- {framework_rules}

Answer with one JSON object and nothing else:
{{"tests": [{{"name": "...", "target": "<the unit id or operation it tests>",
  "kind": "unit|edge|negative|api", "code": "<the whole test file>",
  "description": "<one or two plain sentences: what the test checks>"}}]}}"""

PYTEST_RULES = (
    "Write pytest tests. Import the code under test by its module path (the project root "
    "and src/ are on the import path). One file per test entry; test functions start with "
    "test_. Use pytest.raises for errors and pytest.approx for floats."
)
VITEST_RULES = (
    'Write Vitest tests in TypeScript: import { describe, expect, it } from "vitest". The '
    "test file is written to testforge/<name>.test.ts at the project root, so import the "
    'code under test as "../<path without extension>". Use expect(...).toThrow for errors.'
)
API_RULES = (
    "Write pytest API tests that drive the application object in process: "
    "fastapi.testclient.TestClient(app) for FastAPI, app.test_client() for Flask. Never open "
    "a network connection. Cover every operation listed at least once: assert the status "
    "code is one the operation documents and, for a documented success response, check "
    'the body against its schema. Set target to the operation key, e.g. "GET /items/{id}".'
)


def unit_payload(
    unit: Any, class_examples: list[dict[str, Any]], source_chars: int
) -> dict[str, Any]:
    details = unit.details or {}
    return {
        "id": str(unit.id),
        "kind": unit.kind,
        "name": unit.name,
        "qualname": unit.qualname,
        "module": unit.module,
        "file": unit.file,
        "lines": [unit.start_line, unit.end_line],
        "signature": unit.signature,
        "docstring": unit.docstring,
        "params": details.get("params", []),
        "returns": details.get("returns", ""),
        "examples": details.get("examples", []),
        "raises": details.get("raises", []),
        "class_name": details.get("class_name"),
        "class_examples": class_examples,
        "source": unit.source[:source_chars],
    }


def build(request: dict[str, Any]) -> tuple[str, str]:
    """(system, user) for a generation request."""
    if request["mode"] == "api":
        rules = API_RULES
    else:
        rules = PYTEST_RULES if request["framework"] == "pytest" else VITEST_RULES
    system = SYSTEM.format(framework_rules=rules)
    kinds = ", ".join(request.get("kinds", []))
    intro = (
        f"Write {kinds} tests for the units below."
        if request["mode"] == "unit"
        else "Write API tests for every operation below."
    )
    extra = request.get("instructions") or ""
    user = (
        f"{intro}\n"
        + (f"Extra instructions from the developer: {extra}\n" if extra else "")
        + f"{REQUEST_OPEN}\n{json.dumps(request, indent=1, default=str)}\n{REQUEST_CLOSE}"
    )
    return system, user


def read_request(text: str) -> dict[str, Any] | None:
    """The JSON request inside a prompt (for the mock provider)."""
    start = text.rfind(REQUEST_OPEN)
    end = text.rfind(REQUEST_CLOSE)
    if start == -1 or end == -1 or end < start:
        return None
    try:
        value = json.loads(text[start + len(REQUEST_OPEN) : end])
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


@dataclass
class ParsedTest:
    name: str
    target: str
    kind: str
    code: str
    description: str


class AnswerError(Exception):
    """The model's answer is not the JSON the prompt asked for."""


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def parse_answer(text: str) -> list[ParsedTest]:
    candidates = [text.strip()]
    candidates += [m.group(1).strip() for m in _FENCE.finditer(text)]
    first, last = text.find("{"), text.rfind("}")
    if first != -1 and last > first:
        candidates.append(text[first : last + 1])
    data: Any = None
    for c in candidates:
        try:
            data = json.loads(c)
            break
        except ValueError:
            continue
    if data is None:
        raise AnswerError("The model did not answer with JSON")
    items = data.get("tests") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise AnswerError('The model\'s JSON has no "tests" list')
    out: list[ParsedTest] = []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("code"), str):
            continue
        kind = str(item.get("kind") or "unit")
        out.append(
            ParsedTest(
                name=str(item.get("name") or "generated_test")[:200],
                target=str(item.get("target") or ""),
                kind=kind if kind in ("unit", "edge", "negative", "api") else "unit",
                code=_strip_fence(item["code"]),
                description=str(item.get("description") or "")[:2000],
            )
        )
    return out


def _strip_fence(code: str) -> str:
    m = re.fullmatch(r"\s*```[\w-]*\n(.*?)```\s*", code, re.DOTALL)
    return (m.group(1) if m else code).rstrip() + "\n"
