"""The assertion check (A2): what counts as a real, reachable, grounded assertion."""

from __future__ import annotations

import pytest

from testforge.generation.checks import check

T = {"price"}


@pytest.mark.parametrize(
    "code",
    [
        "def test_a():\n    assert price(2) == 4\n",
        "import pytest\n\ndef test_a():\n    with pytest.raises(ValueError):\n        price(-1)\n",
        "import pytest\n\ndef test_a():\n    pytest.raises(ValueError, price, -1)\n",
        "class TestPrice:\n    def test_a(self):\n        self.assertEqual(price(2), 4)\n",
        "def check(x):\n    assert x > 0\n\ndef test_a():\n    check(price(2))\n",
        "def test_a():\n    for n in (1, 2):\n        assert price(n) > 0\n",
        "def test_a():\n    if price(1):\n        assert price(1) == 2\n",
        "def test_a():\n    try:\n        assert price(1) == 2\n    finally:\n        pass\n",
        "async def test_a():\n    assert await price(1) == 2\n",
    ],
)
def test_python_real_assertions_pass(code: str) -> None:
    result = check("python", code, T)
    assert result.ok, result.reason
    assert result.summary()


@pytest.mark.parametrize(
    ("code", "reason"),
    [
        ("def test_a():\n    price(2)\n", "no_assertion"),
        ("def test_a():\n    assert True\n", "no_assertion"),
        ("def test_a():\n    assert 1\n", "no_assertion"),
        ("def test_a():\n    assert (1, 2)\n", "no_assertion"),
        ("def test_a():\n    x = price(1)\n    assert x == x\n", "no_assertion"),
        ("def test_a():\n    assert 1 == 1\n", "no_assertion"),
        ("def test_a():\n    assert price(1) or True\n", "no_assertion"),
        ("def test_a():\n    return\n    assert price(1) == 2\n", "no_assertion"),
        ("def test_a():\n    raise RuntimeError\n    assert price(1) == 2\n", "no_assertion"),
        (
            "import pytest\n\ndef test_a():\n    pytest.skip('x')\n    assert price(1) == 2\n",
            "no_assertion",
        ),
        ("def test_a():\n    if False:\n        assert price(1) == 2\n", "no_assertion"),
        ("def test_a():\n    while 0:\n        assert price(1) == 2\n", "no_assertion"),
        (
            "import pytest\n\ndef test_a():\n    with pytest.raises(ValueError):\n        pass\n",
            "no_assertion",
        ),
        ("def test_a():\n    assert len([1]) == 1\n", "not_grounded"),
        ("def helper():\n    assert price(1)\n", "no_tests"),
        ("def test_a(:\n", "syntax_error"),
        (
            "def test_a():\n    assert price(1) == 2\n\ndef test_b():\n    assert True\n",
            "no_assertion",
        ),
    ],
)
def test_python_placeholders_and_unreachable_assertions_are_refused(code: str, reason: str) -> None:
    result = check("python", code, T)
    assert not result.ok
    assert result.code == reason, result.reason


def test_module_level_client_counts_as_calling_the_target() -> None:
    code = (
        "from fastapi.testclient import TestClient\nfrom app.main import app\n"
        "client = TestClient(app)\n\ndef test_a():\n    r = client.get('/x')\n    assert r.status_code == 200\n"
    )
    assert check("python", code, {"get"}).ok


@pytest.mark.parametrize(
    "code",
    [
        'import { expect, it } from "vitest";\nit("a", () => {\n  expect(price(2)).toBe(4);\n});\n',
        'it("a", async () => {\n  await expect(price(2)).resolves.toEqual(4);\n});\n',
        'it("a", () => {\n  expect(() => price(-1)).toThrow(RangeError);\n});\n',
        'test("a", function () {\n  expect(new price(1).x).not.toBeNull();\n});\n',
        'describe("p", () => {\n  it("a", () => expect(price(1)).toBeCloseTo(1.5));\n});\n',
        'it("a", () => {\n  assert.equal(price(1), 2);\n});\n',
    ],
)
def test_javascript_real_assertions_pass(code: str) -> None:
    result = check("typescript", code, T)
    assert result.ok, result.reason


@pytest.mark.parametrize(
    ("code", "reason"),
    [
        ('it("a", () => {\n  price(1);\n});\n', "no_assertion"),
        ('it("a", () => {\n  price(1);\n  expect(true).toBe(true);\n});\n', "no_assertion"),
        ('it("a", () => {\n  const x = price(1);\n  expect(x).toBe(x);\n});\n', "no_assertion"),
        ('it("a", () => {\n  expect(price(1));\n});\n', "no_assertion"),
        ('it("a", () => {\n  return;\n  expect(price(1)).toBe(2);\n});\n', "no_assertion"),
        (
            'it("a", () => {\n  if (false) {\n    expect(price(1)).toBe(2);\n  }\n});\n',
            "no_assertion",
        ),
        ('it("a", () => {\n  expect([1].length).toBe(1);\n});\n', "not_grounded"),
        ("const x = 1;\n", "no_tests"),
        ('it("a", () => {\n  expect(price(1).toBe(2);\n});\n', "syntax_error"),
        ('it("a", () => {\n  // expect(price(1)).toBe(2);\n});\n', "no_assertion"),
    ],
)
def test_javascript_placeholders_are_refused(code: str, reason: str) -> None:
    result = check("typescript", code, T)
    assert not result.ok
    assert result.code == reason, result.reason


def test_skipped_and_todo_tests_are_not_counted() -> None:
    code = 'it.skip("a", () => {});\nit.todo("b");\nit("c", () => {\n  expect(price(1)).toBe(2);\n});\n'
    assert check("javascript", code, T).ok
