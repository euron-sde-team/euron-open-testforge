"""Test code built from facts in the analyzed source: documented examples, the conditions
under which a unit raises, and the operations of an OpenAPI document.

The deterministic mock provider writes its tests with these builders, and API generation
uses them to cover any documented operation a model skipped (A7). Every value in a test
comes from the source or the specification, never from guessing what the code does.
"""

from __future__ import annotations

import ast
import builtins
import json
import re
from dataclasses import dataclass
from typing import Any

from testforge.analysis import jslex

PY_TEST_DIR = "tests/testforge"
JS_TEST_DIR = "testforge"


@dataclass
class Draft:
    name: str
    kind: str  # unit, edge, negative, api
    target: str  # a unit id, or an operation key ("GET /items/{id}")
    code: str
    description: str


def slug(text: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").lower()
    return s[:60] or "case"


# ── Values ───────────────────────────────────────────────────────────────────────────


def _py_literal(text: str) -> str | None:
    """The documented output as Python source, when it is a literal."""
    try:
        value = ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return None
    return repr(value)


def _is_float_literal(text: str) -> bool:
    try:
        return isinstance(ast.literal_eval(text), float)
    except (ValueError, SyntaxError):
        return False


def _py_call_args(expression: str, name: str) -> list[str] | None:
    """Positional arguments of the first call to ``name`` in an expression."""
    try:
        tree = ast.parse(expression, mode="exec")
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            called = (
                f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
            )
            if called == name and not node.keywords:
                return [ast.unparse(a) for a in node.args]
    return None


TYPE_DEFAULTS_PY = {
    "int": "1",
    "float": "1.0",
    "str": "'a'",
    "bool": "True",
    "list": "[]",
    "dict": "{}",
}
TYPE_DEFAULTS_JS = {"number": "1", "string": '"a"', "boolean": "true"}


def _violations(
    condition: str, params: list[str], base: dict[str, str]
) -> list[tuple[str, str, str]]:
    """For ``if <condition>: raise``: (param, value, kind) assignments that make the
    condition true, for conditions made of ``param <op> number`` (joined by or / ||) or
    ``param <op> other_param``. ``kind`` is edge (the boundary) or negative."""
    out: list[tuple[str, str, str]] = []
    parts = re.split(r"\bor\b|\|\|", condition)
    for part in parts:
        m = re.fullmatch(r"\s*([A-Za-z_]\w*)\s*(<=|<|>=|>|==|===)\s*(-?\d+(?:\.\d+)?)\s*", part)
        if m and m.group(1) in params:
            name, op, num = m.group(1), m.group(2), float(m.group(3))
            is_int = "." not in m.group(3)

            def fmt(v: float, is_int: bool = is_int) -> str:
                return str(int(v)) if is_int else repr(v)

            if op == "<=":
                out += [(name, fmt(num), "edge"), (name, fmt(num - 1), "negative")]
            elif op == "<":
                out.append((name, fmt(num - 1), "negative"))
            elif op == ">=":
                out += [(name, fmt(num), "edge"), (name, fmt(num + 1), "negative")]
            elif op == ">":
                out.append((name, fmt(num + 1), "negative"))
            continue
        m = re.fullmatch(r"\s*([A-Za-z_]\w*)\s*(<|>)\s*([A-Za-z_]\w*)\s*", part)
        if m and m.group(1) in params and m.group(3) in params:
            left, op, right = m.groups()
            other = base.get(right)
            if other is None or not re.fullmatch(r"-?\d+(?:\.\d+)?", other):
                continue
            n = float(other)
            is_int = "." not in other
            value = n + 1 if op == ">" else n - 1
            out.append((left, str(int(value)) if is_int else repr(value), "edge"))
            continue
        m = re.fullmatch(r"\s*!\s*Number\.isInteger\(\s*([A-Za-z_]\w*)\s*\)\s*", part)
        if m and m.group(1) in params:
            out.append((m.group(1), "1.5", "negative"))
    return out


# ── Python ───────────────────────────────────────────────────────────────────────────


def python_example_tests(unit: dict[str, Any]) -> list[Draft]:
    examples = list(unit.get("examples") or [])
    if unit.get("kind") == "method":
        # A method's own examples, else the class's examples that end in a call to it.
        examples += [
            e for e in unit.get("class_examples") or [] if f".{unit['name']}(" in e["expression"]
        ]
    tests: list[str] = []
    asserts: list[str] = []
    approx = False
    for i, ex in enumerate(examples, 1):
        expected = _py_literal(ex["expected"])
        if expected is None:
            continue
        called = unit["name"] if unit["kind"] != "class" else ""
        if called and f"{called}(" not in ex["expression"] and unit["kind"] != "class":
            continue
        rhs = expected
        if _is_float_literal(ex["expected"]):
            rhs, approx = f"pytest.approx({expected})", True
        body = [f"    {line}" for line in ex.get("setup", [])]
        body.append(f"    assert {ex['expression']} == {rhs}")
        tests.append(f"def test_{slug(unit['name'])}_example_{i}():\n" + "\n".join(body) + "\n")
        asserts.append(f"{ex['expression']} == {expected}")
    if not tests:
        return []
    header = (
        f'"""Documented examples of {unit["qualname"]}, checked as tests (written by TestForge)."""\n\n'
        + ("import pytest\n\n" if approx else "")
        + f"from {unit['module']} import {unit.get('class_name') or unit['name']}\n\n\n"
    )
    return [
        Draft(
            name=f"test_{slug(unit['name'])}_examples",
            kind="unit",
            target=unit["id"],
            code=header + "\n\n".join(tests),
            description=(
                f"Checks that {unit['qualname']} returns what its documentation says: "
                + "; ".join(asserts[:4])
                + ("." if len(asserts) <= 4 else ", and more.")
            ),
        )
    ]


def _py_base_args(unit: dict[str, Any]) -> dict[str, str] | None:
    params = [p for p in unit.get("params", []) if p["kind"] == "positional"]
    sources = [e["expression"] for e in unit.get("examples") or []]
    sources += [s for e in unit.get("class_examples") or [] for s in e.get("setup", [])]
    for expr in sources:
        args = _py_call_args(expr, unit["name"])
        if args is not None and len(args) <= len(params):
            base = {p["name"]: a for p, a in zip(params, args, strict=False)}
            for p in params[len(args) :]:
                if p["default"] is None:
                    break
                base[p["name"]] = p["default"]
            else:
                return base
    base = {}
    for p in params:
        if p["default"] is not None:
            base[p["name"]] = p["default"]
        elif p["annotation"] in TYPE_DEFAULTS_PY:
            base[p["name"]] = TYPE_DEFAULTS_PY[p["annotation"]]
        else:
            return None
    return base


def _py_receiver(unit: dict[str, Any]) -> tuple[list[str], str] | None:
    """Setup lines and the receiver for a method call, from the class's own examples."""
    for ex in unit.get("class_examples") or []:
        setup = ex.get("setup") or []
        if setup and re.match(r"^\w+\s*=\s*" + re.escape(unit["class_name"]) + r"\(", setup[0]):
            return [setup[0]], setup[0].split("=")[0].strip()
    return None


def python_raise_tests(unit: dict[str, Any]) -> list[Draft]:
    base = _py_base_args(unit)
    if base is None:
        return []
    order = [p["name"] for p in unit.get("params", []) if p["kind"] == "positional"]
    receiver: tuple[list[str], str] | None = None
    if unit["kind"] == "method":
        receiver = _py_receiver(unit)
        if receiver is None:
            return []
    drafts: list[Draft] = []
    seen: set[tuple[str, str]] = set()
    for r in unit.get("raises") or []:
        if not r.get("condition"):
            continue
        for name, value, kind in _violations(r["condition"], order, base):
            if (name, value) in seen:
                continue
            seen.add((name, value))
            args = ", ".join(value if p == name else base[p] for p in order if p in base)
            call = f"{unit['name']}({args})"
            setup: list[str] = []
            if receiver is not None:
                setup, obj = receiver
                call = f"{obj}.{call}"
            exc = r["exception"].rsplit(".", 1)[-1]
            if not hasattr(builtins, exc):
                continue  # a project's own error class would need its import path
            body = "\n".join(f"    {s}" for s in setup)
            body += ("\n" if body else "") + f"    with pytest.raises({exc}):\n        {call}\n"
            test_name = f"test_{slug(unit['name'])}_raises_when_{slug(name)}_is_{slug(value.replace('-', 'minus '))}"
            code = (
                f'"""{"Boundary" if kind == "edge" else "Negative"} test for {unit["qualname"]}: '
                f'it must refuse {name}={value} (written by TestForge)."""\n\n'
                "import pytest\n\n"
                f"from {unit['module']} import {unit.get('class_name') or unit['name']}\n\n\n"
                f"def {test_name}():\n{body}"
            )
            drafts.append(
                Draft(
                    name=test_name,
                    kind=kind,
                    target=unit["id"],
                    code=code,
                    description=(
                        f"Calls {unit['qualname']} with {name}={value}, which makes "
                        f"`{r['condition']}` true, and expects {exc}"
                        + (f' ("{r["message"]}")' if r.get("message") else "")
                        + (". This is the boundary value." if kind == "edge" else ".")
                    ),
                )
            )
    return drafts


def python_smoke_test(unit: dict[str, Any]) -> Draft:
    """A call with no assertion: what a model writes when it cannot ground a test. The
    assertion check refuses it; the mock writes it on purpose so that guard is visible."""
    base = _py_base_args(unit) or {}
    args = ", ".join(base.values())
    owner = unit.get("class_name") or unit["name"]
    call = f"{owner}()" if unit["kind"] == "class" else f"{unit['name']}({args})"
    if unit["kind"] == "method":
        call = f"{owner}().{unit['name']}({args})"
    name = f"test_{slug(unit['name'])}_runs"
    return Draft(
        name=name,
        kind="unit",
        target=unit["id"],
        code=f"from {unit['module']} import {owner}\n\n\ndef {name}():\n    {call}\n",
        description=f"Calls {unit['qualname']}.",
    )


# ── JavaScript and TypeScript ────────────────────────────────────────────────────────


def _js_import(unit: dict[str, Any]) -> str:
    target = unit.get("class_name") or unit["name"]
    return f'import {{ {target} }} from "../{unit["module"]}";\n'


def _js_expected(text: str) -> tuple[str, str] | None:
    t = text.strip().rstrip(";")
    if re.fullmatch(r"-?\d+", t) or t in ("true", "false", "null", "undefined"):
        return "toBe", t
    if re.fullmatch(r"-?\d+\.\d+", t):
        return "toBeCloseTo", t
    if re.fullmatch(r"\"[^\"\\]*\"|'[^'\\]*'", t):
        return "toBe", json.dumps(t[1:-1])
    if t.startswith(("[", "{")):
        return "toEqual", t
    return None


def js_example_tests(unit: dict[str, Any]) -> list[Draft]:
    examples = list(unit.get("examples") or [])
    cases: list[str] = []
    asserts: list[str] = []
    for i, ex in enumerate(examples, 1):
        if unit["kind"] == "method" and f".{unit['name']}(" not in ex["expression"]:
            continue
        if unit["kind"] == "function" and f"{unit['name']}(" not in ex["expression"]:
            continue
        expected = _js_expected(ex["expected"])
        if expected is None:
            continue
        matcher, value = expected
        lines = [f"    {s}" for s in ex.get("setup", [])]
        lines.append(f"    expect({ex['expression']}).{matcher}({value});")
        cases.append(
            f'  it("matches documented example {i}", () => {{\n' + "\n".join(lines) + "\n  });\n"
        )
        asserts.append(f"{ex['expression']} is {ex['expected']}")
    if not cases:
        return []
    label = f"{unit['class_name']}.{unit['name']}" if unit.get("class_name") else unit["name"]
    code = (
        f"// Documented examples of {unit['qualname']}, checked as tests (written by TestForge).\n"
        'import { describe, expect, it } from "vitest";\n'
        + _js_import(unit)
        + f'\ndescribe("{label}", () => {{\n'
        + "\n".join(cases)
        + "});\n"
    )
    return [
        Draft(
            name=f"{slug(label)}_examples",
            kind="unit",
            target=unit["id"],
            code=code,
            description=f"Checks that {unit['qualname']} returns what its JSDoc says: "
            + "; ".join(asserts[:4])
            + ".",
        )
    ]


def _js_call_args(expression: str, name: str) -> list[str] | None:
    masked = jslex.mask(expression)
    m = re.search(rf"(?:^|[^\w$]){re.escape(name)}\s*\(", masked)
    if not m:
        return None
    open_at = m.end() - 1
    close = jslex.match_close(masked, open_at)
    if close == -1:
        return None
    return jslex.split_top_level(masked, expression, open_at + 1, close)


def _js_base_args(unit: dict[str, Any]) -> dict[str, str] | None:
    params = [p for p in unit.get("params", []) if p["kind"] == "positional"]
    sources = [e["expression"] for e in unit.get("examples") or []]
    sources += [s for e in unit.get("examples") or [] for s in e.get("setup", [])]
    for expr in sources:
        args = _js_call_args(expr, unit["name"])
        if (args is not None and len(args) == len([p for p in params if p["default"] is None])) or (
            args is not None and len(args) == len(params)
        ):
            return {p["name"]: a for p, a in zip(params, args or [], strict=False)}
    base = {}
    for p in params:
        if p["default"] is not None:
            base[p["name"]] = p["default"]
        elif p["annotation"] in TYPE_DEFAULTS_JS:
            base[p["name"]] = TYPE_DEFAULTS_JS[p["annotation"]]
        else:
            return None
    return base


def js_raise_tests(unit: dict[str, Any]) -> list[Draft]:
    base = _js_base_args(unit)
    if base is None:
        return []
    order = [p["name"] for p in unit.get("params", []) if p["kind"] == "positional"]
    setup: list[str] = []
    receiver = ""
    if unit["kind"] == "method":
        for ex in unit.get("examples") or []:
            first = (ex.get("setup") or [""])[0]
            m = re.match(
                r"^(?:const|let)\s+(\w+)\s*=\s*new\s+"
                + re.escape(unit["class_name"] or "")
                + r"\(",
                first,
            )
            if m:
                setup, receiver = [first], m.group(1) + "."
                break
        if not receiver:
            return []
    cases: list[str] = []
    notes: list[str] = []
    kinds: set[str] = set()
    for r in unit.get("raises") or []:
        if not r.get("condition"):
            continue
        for name, value, kind in _violations(r["condition"], order, base):
            args = ", ".join(value if p == name else base[p] for p in order if p in base)
            lines = [f"    {s}" for s in setup]
            lines.append(
                f"    expect(() => {receiver}{unit['name']}({args})).toThrow({r['exception']});"
            )
            cases.append(
                f'  it("throws {r["exception"]} when {name} is {value}", () => {{\n'
                + "\n".join(lines)
                + "\n  });\n"
            )
            notes.append(f"{name}={value} makes `{r['condition']}` true")
            kinds.add(kind)
    if not cases:
        return []
    label = f"{unit['class_name']}.{unit['name']}" if unit.get("class_name") else unit["name"]
    code = (
        f"// Edge and negative cases of {unit['qualname']} (written by TestForge).\n"
        'import { describe, expect, it } from "vitest";\n'
        + _js_import(unit)
        + f'\ndescribe("{label} refuses invalid input", () => {{\n'
        + "\n".join(cases)
        + "});\n"
    )
    return [
        Draft(
            name=f"{slug(label)}_refuses_invalid_input",
            kind="edge" if kinds == {"edge"} else "negative",
            target=unit["id"],
            code=code,
            description=f"Checks that {unit['qualname']} throws for invalid input: "
            + "; ".join(notes[:4])
            + ".",
        )
    ]


def js_smoke_test(unit: dict[str, Any]) -> Draft:
    base = _js_base_args(unit) or {}
    owner = unit.get("class_name") or unit["name"]
    call = (
        f"new {owner}()"
        if unit["kind"] == "class"
        else f"{unit['name']}({', '.join(base.values())})"
    )
    if unit["kind"] == "method":
        call = f"new {owner}().{unit['name']}({', '.join(base.values())})"
    label = slug(unit["name"])
    return Draft(
        name=f"{label}_runs",
        kind="unit",
        target=unit["id"],
        code='import { it } from "vitest";\n'
        + _js_import(unit)
        + f'\nit("runs", () => {{\n  {call};\n}});\n',
        description=f"Calls {unit['qualname']}.",
    )


# ── API tests from OpenAPI operations ────────────────────────────────────────────────


def sample_value(schema: dict[str, Any], doc: dict[str, Any], depth: int = 0) -> Any:
    """A value valid for ``schema``: its example or default when the document gives one,
    else the simplest value of its type."""
    schema = resolve(schema, doc)
    for key in ("example", "default"):
        if key in schema:
            return schema[key]
    if schema.get("examples") and isinstance(schema["examples"], list):
        return schema["examples"][0]
    if schema.get("enum"):
        return schema["enum"][0]
    for combo in ("anyOf", "oneOf", "allOf"):
        if schema.get(combo):
            options = [o for o in schema[combo] if resolve(o, doc).get("type") != "null"]
            if options:
                return sample_value(options[0], doc, depth + 1)
    kind = schema.get("type")
    if kind == "integer":
        return max(int(schema.get("minimum", 1)), 1)
    if kind == "number":
        return float(max(schema.get("minimum", 1), 1))
    if kind == "boolean":
        return True
    if kind == "array":
        if depth > 3:
            return []
        return [sample_value(schema.get("items", {}), doc, depth + 1)]
    if kind == "object" or "properties" in schema:
        if depth > 3:
            return {}
        required = schema.get("required", [])
        props = schema.get("properties", {})
        return {k: sample_value(v, doc, depth + 1) for k, v in props.items() if k in required}
    return "example"


def resolve(schema: dict[str, Any], doc: dict[str, Any]) -> dict[str, Any]:
    seen = 0
    while isinstance(schema, dict) and "$ref" in schema and seen < 20:
        ref = str(schema["$ref"])
        node: Any = doc
        for part in ref.lstrip("#/").split("/"):
            node = node.get(part, {}) if isinstance(node, dict) else {}
        schema = node if isinstance(node, dict) else {}
        seen += 1
    return schema if isinstance(schema, dict) else {}


def _keys_of(schema: dict[str, Any], doc: dict[str, Any]) -> list[str]:
    schema = resolve(schema, doc)
    required = schema.get("required") or []
    return [k for k in schema.get("properties", {}) if k in required][:8]


def api_test(op: dict[str, Any], app: dict[str, str], doc: dict[str, Any]) -> Draft:
    """One in-process test for one documented operation: the status code is one the
    document lists, and a successful response has the documented shape."""
    method = op["method"].lower()
    path = op["path"]
    for param in op.get("parameters", []):
        if param.get("in") == "path":
            value = sample_value(param.get("schema", {}), doc)
            path = path.replace("{" + param["name"] + "}", str(value))
    query = {
        p["name"]: sample_value(p.get("schema", {}), doc)
        for p in op.get("parameters", [])
        if p.get("in") == "query" and p.get("required")
    }
    codes = sorted({int(c) for c in op.get("responses", {}) if str(c).isdigit()}) or [200]
    success = next((c for c in codes if 200 <= c < 300), None)
    body_schema = op.get("request_body")
    flask = app["framework"] == "flask"
    args = [repr(path)]
    if query:
        args.append(f"{'query_string' if flask else 'params'}={query!r}")
    if body_schema is not None:
        args.append(f"json={sample_value(body_schema, doc)!r}")
    call = f"client.{method}({', '.join(args)})"
    json_of = "response.get_json()" if flask else "response.json()"
    lines = [
        f"    response = {call}",
        f"    assert response.status_code in {tuple(codes)!r}, response.text"
        if not flask
        else f"    assert response.status_code in {tuple(codes)!r}",
    ]
    response_schema = resolve(
        op.get("responses", {}).get(str(success), {}).get("schema") or {}, doc
    )
    shape = ""
    if success is not None and response_schema:
        lines.append(f"    if response.status_code == {success}:")
        lines.append(f"        body = {json_of}")
        if response_schema.get("type") == "array":
            lines.append("        assert isinstance(body, list)")
            keys = _keys_of(response_schema.get("items", {}), doc)
            if keys:
                lines.append("        for item in body:")
                lines.append(f"            assert set({keys!r}) <= set(item)")
                shape = f"a list of objects with {', '.join(keys)}"
            else:
                shape = "a list"
        elif response_schema.get("type") == "object" or "properties" in response_schema:
            lines.append("        assert isinstance(body, dict)")
            keys = _keys_of(response_schema, doc)
            if keys:
                lines.append(f"        assert set({keys!r}) <= set(body)")
                shape = f"an object with {', '.join(keys)}"
            else:
                shape = "an object"
    name = f"test_{slug(op.get('operation_id') or method + '_' + op['path'])}"
    setup = "client = app.test_client()" if flask else "client = TestClient(app)"
    header = (
        f'"""API test for {op["method"]} {op["path"]}, from the imported OpenAPI document '
        '(written by TestForge). Runs in process: the sandbox has no network."""\n\n'
        + ("" if flask else "from fastapi.testclient import TestClient\n\n")
        + f"from {app['module']} import {app['attr']}"
        + (" as app\n\n" if app["attr"] != "app" else "\n\n")
        + f"{setup}\n\n\n"
    )
    code = header + f"def {name}():\n" + "\n".join(lines) + "\n"
    description = (
        f"Sends {op['method']} {path} to the app and checks the status code is one the document "
        f"lists ({', '.join(map(str, codes))})"
        + (f"; on {success} the body must be {shape}." if shape else ".")
    )
    return Draft(
        name=name,
        kind="api",
        target=f"{op['method']} {op['path']}",
        code=code,
        description=description,
    )


def api_negative_test(op: dict[str, Any], app: dict[str, str], doc: dict[str, Any]) -> Draft | None:
    """An operation with a JSON body and a documented 422 must refuse an empty body."""
    codes = {str(c) for c in op.get("responses", {})}
    if op.get("request_body") is None or "422" not in codes or app["framework"] != "fastapi":
        return None
    name = f"test_{slug(op.get('operation_id') or op['method'] + '_' + op['path'])}_refuses_an_invalid_body"
    path = op["path"]
    for param in op.get("parameters", []):
        if param.get("in") == "path":
            path = path.replace(
                "{" + param["name"] + "}", str(sample_value(param.get("schema", {}), doc))
            )
    code = (
        f'"""Negative API test for {op["method"]} {op["path"]} (written by TestForge)."""\n\n'
        "from fastapi.testclient import TestClient\n\n"
        f"from {app['module']} import {app['attr']}"
        + (" as app" if app["attr"] != "app" else "")
        + "\n\n"
        "client = TestClient(app)\n\n\n"
        f"def {name}():\n"
        f"    response = client.{op['method'].lower()}({path!r}, json={{}})\n"
        "    assert response.status_code == 422\n"
    )
    return Draft(
        name=name,
        kind="negative",
        target=f"{op['method']} {op['path']}",
        code=code,
        description=f"Sends {op['method']} {path} with an empty JSON body and expects the documented 422.",
    )
