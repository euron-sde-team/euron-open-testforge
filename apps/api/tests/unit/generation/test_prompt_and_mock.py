"""Prompt assembly, answer parsing, the deterministic mock model and the test templates."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from testforge.analysis import analyzer
from testforge.generation import checks, prompt, templates
from testforge.providers.mock.responder import explain, respond
from testforge.specs import openapi

DEMO = Path(__file__).parents[3] / "src" / "testforge" / "demo" / "projects"


def _payloads(name: str) -> tuple[list[dict[str, Any]], Any]:
    root = DEMO / name
    files = {
        str(p.relative_to(root)): p.read_text()
        for p in root.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    }
    a, _ = analyzer.analyze(files)
    classes = {u.name: [e.as_dict() for e in u.examples] for u in a.units if u.kind == "class"}
    out = []
    for u in a.units:
        row = SimpleNamespace(
            id=uuid.uuid4(),
            kind=u.kind,
            name=u.name,
            qualname=u.qualname,
            module=u.module,
            file=u.file,
            start_line=u.start_line,
            end_line=u.end_line,
            signature=u.signature,
            docstring=u.docstring,
            details=u.details(),
            source=u.source,
        )
        out.append(prompt.unit_payload(row, classes.get(u.class_name or u.name, []), 2000))
    return out, a


def test_prompt_carries_the_real_source_as_json() -> None:
    units, _ = _payloads("python-shop")
    split = next(u for u in units if u["name"] == "split_bill")
    system, user = prompt.build(
        {
            "mode": "unit",
            "framework": "pytest",
            "kinds": ["unit"],
            "units": [split],
            "instructions": "focus on rounding",
        }
    )
    assert "Every test must contain at least one real assertion" in system
    assert "pytest" in system
    assert "focus on rounding" in user
    req = prompt.read_request(user)
    assert (
        req is not None
        and req["units"][0]["signature"]
        == "def split_bill(total: float, people: int) -> list[float]"
    )
    assert "[33.34, 33.33, 33.33]" in req["units"][0]["docstring"]
    _, vitest_user = prompt.build(
        {"mode": "unit", "framework": "vitest", "kinds": ["unit"], "units": []}
    )
    assert prompt.read_request(vitest_user) == {
        "mode": "unit",
        "framework": "vitest",
        "kinds": ["unit"],
        "units": [],
    }
    api_system, _ = prompt.build({"mode": "api", "framework": "pytest", "operations": []})
    assert "TestClient" in api_system
    assert prompt.read_request("no request here") is None
    assert prompt.read_request(f"{prompt.REQUEST_OPEN}[1]{prompt.REQUEST_CLOSE}") is None


def test_answers_are_parsed_from_json_or_fenced_json() -> None:
    body = {
        "tests": [
            {
                "name": "t",
                "target": "x",
                "kind": "weird",
                "code": "```python\nassert 1\n```",
                "description": "d",
            },
            {"bad": 1},
        ]
    }
    for text in (
        json.dumps(body),
        f"Here you go:\n```json\n{json.dumps(body)}\n```",
        f"prefix {json.dumps(body)} suffix",
    ):
        tests = prompt.parse_answer(text)
        assert len(tests) == 1
        assert tests[0].kind == "unit" and tests[0].code == "assert 1\n"
    assert prompt.parse_answer(json.dumps([{"code": "x"}]))[0].name == "generated_test"
    with pytest.raises(prompt.AnswerError):
        prompt.parse_answer("I cannot do that")
    with pytest.raises(prompt.AnswerError):
        prompt.parse_answer('{"nope": 1}')


def test_mock_writes_grounded_python_tests_and_one_refusable_call() -> None:
    units, _ = _payloads("python-shop")
    system, user = prompt.build(
        {
            "mode": "unit",
            "framework": "pytest",
            "kinds": ["unit", "edge", "negative"],
            "units": units,
        }
    )
    tests = prompt.parse_answer(respond(system, user))
    names = {t.name for t in tests}
    assert "test_split_bill_examples" in names
    assert "test_reserve_raises_when_quantity_is_0" in names
    assert "test_reserve_raises_when_quantity_is_11" in names  # quantity > stock, stock=10
    by_target = {u["id"]: u for u in units}
    outcomes = []
    for t in tests:
        unit = by_target[t.target]
        targets = {unit["name"], unit.get("class_name") or unit["name"]}
        outcomes.append((t.name, checks.check("python", t.code, targets).ok))
    refused = [n for n, ok in outcomes if not ok]
    assert refused and all(n.endswith("_runs") for n in refused)
    # Same prompt, same answer.
    assert respond(system, user) == respond(system, user)


def test_mock_writes_grounded_typescript_tests() -> None:
    units, _ = _payloads("ts-toolkit")
    system, user = prompt.build(
        {"mode": "unit", "framework": "vitest", "kinds": ["unit", "negative"], "units": units}
    )
    tests = prompt.parse_answer(respond(system, user))
    clamp = next(t for t in tests if t.name == "clamp_examples")
    assert "expect(clamp(15, 0, 10)).toBe(10);" in clamp.code
    assert 'import { clamp } from "../src/validate";' in clamp.code
    tip = next(t for t in tests if t.name == "addtip_refuses_invalid_input")
    assert "toThrow(RangeError)" in tip.code and "addTip(1000, -1)" in tip.code
    fmt = next(t for t in tests if t.name == "formatprice_refuses_invalid_input")
    assert "formatPrice(1.5" in fmt.code
    basket = next(t for t in tests if t.name == "basket_count_examples")
    assert "const basket = new Basket();" in basket.code


def test_mock_writes_one_api_test_per_operation() -> None:
    _, analysis = _payloads("python-shop")
    doc = openapi.load((DEMO / "python-shop-openapi.json").read_text())
    ops = openapi.operations(doc)
    app = {k: v for k, v in analysis.apps[0].as_dict().items() if k != "file"}
    system, user = prompt.build(
        {"mode": "api", "framework": "pytest", "app": app, "operations": ops, "document": doc}
    )
    tests = prompt.parse_answer(respond(system, user))
    assert {t.target for t in tests} == {op["key"] for op in ops}
    negative = [t for t in tests if t.kind == "negative"]
    assert len(negative) == 1 and "== 422" in negative[0].code
    for t in tests:
        assert checks.check("python", t.code, {"get", "post"}).ok, t.name


def test_flask_api_template() -> None:
    op = {
        "method": "GET",
        "path": "/ping",
        "operation_id": "",
        "parameters": [
            {"name": "q", "in": "query", "required": True, "schema": {"type": "integer"}}
        ],
        "request_body": None,
        "responses": {
            "200": {
                "schema": {
                    "type": "array",
                    "items": {"type": "object", "properties": {"a": {}}, "required": ["a"]},
                }
            }
        },
    }
    d = templates.api_test(op, {"framework": "flask", "module": "web", "attr": "server"}, {})
    assert "client = app.test_client()" in d.code
    assert "from web import server as app" in d.code
    assert "query_string={'q': 1}" in d.code
    assert "response.get_json()" in d.code
    assert checks.check("python", d.code, {"get"}).ok


def test_sample_values_follow_the_schema() -> None:
    doc = {
        "components": {
            "schemas": {
                "Item": {
                    "type": "object",
                    "required": ["n", "tags"],
                    "properties": {
                        "n": {"type": "integer", "minimum": 5},
                        "tags": {"type": "array", "items": {"type": "string", "enum": ["a", "b"]}},
                        "x": {"type": "string"},
                    },
                }
            }
        }
    }
    assert templates.sample_value({"$ref": "#/components/schemas/Item"}, doc) == {
        "n": 5,
        "tags": ["a"],
    }
    assert templates.sample_value({"anyOf": [{"type": "null"}, {"type": "boolean"}]}, doc) is True
    assert templates.sample_value({"type": "string", "example": "hi"}, doc) == "hi"
    assert templates.sample_value({"type": "number"}, doc) == 1.0
    assert templates.slug("GET /a/{b}") == "get_a_b"


def test_explanations_from_the_mock() -> None:
    text = explain({"test": "t", "compare": {"left": "1", "right": "2", "operator": "=="}})
    assert "returned 1" in text and "expected 2" in text
    assert "failed with boom" in explain({"test": "t", "message": "boom"})
    assert respond("", "hello").startswith("TestForge mock model")
    req = {"mode": "explain", "failure": {"test": "t", "message": "x"}}
    assert "t failed" in respond(
        "", f"{prompt.REQUEST_OPEN}{json.dumps(req)}{prompt.REQUEST_CLOSE}"
    )
