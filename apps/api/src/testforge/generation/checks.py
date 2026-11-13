"""The assertion check every generated test must pass before anyone sees it (A2).

A generated test file is rejected when any test in it:

* has no assertion at all, or only a placeholder (``assert True``, ``assert 1``,
  ``expect(true).toBe(true)``, ``expect(x).toBe(x)``);
* has its only assertions where they can never run (after an unconditional ``return``,
  ``raise`` or ``pytest.skip``, inside ``if False:``);
* never calls the code under test (an assertion about nothing the project contains).

The file must also parse (Python) or have balanced brackets (JavaScript and TypeScript),
and contain at least one test. The check reads the code only; it never runs it.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field

from testforge.analysis import jslex


@dataclass
class Assertion:
    line: int
    text: str


@dataclass
class TestCheck:
    name: str
    line: int
    assertions: list[Assertion] = field(default_factory=list)
    calls_target: bool = False

    __test__ = False


@dataclass
class CheckResult:
    ok: bool
    code: str = ""
    reason: str = ""
    tests: list[TestCheck] = field(default_factory=list)

    def summary(self) -> list[dict[str, object]]:
        return [
            {"test": t.name, "line": a.line, "text": a.text}
            for t in self.tests
            for a in t.assertions
        ]


def _reject(code: str, reason: str, tests: list[TestCheck] | None = None) -> CheckResult:
    return CheckResult(False, code, reason, tests or [])


def _verdict(tests: list[TestCheck]) -> CheckResult:
    if not tests:
        return _reject("no_tests", "The file contains no test function")
    for t in tests:
        if not t.assertions:
            return _reject(
                "no_assertion",
                f"{t.name} has no meaningful assertion that can run (a test that cannot fail "
                "proves nothing)",
                tests,
            )
        if not t.calls_target:
            return _reject(
                "not_grounded",
                f"{t.name} never calls the code it is meant to test",
                tests,
            )
    return CheckResult(True, tests=tests)


# ── Python ───────────────────────────────────────────────────────────────────────────


def _truthy_constant(node: ast.expr) -> bool:
    if isinstance(node, ast.Constant):
        return bool(node.value)
    if isinstance(node, ast.Tuple | ast.List | ast.Set):
        return len(node.elts) > 0
    if isinstance(node, ast.Dict):
        return len(node.keys) > 0
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return isinstance(node.operand, ast.Constant) and not node.operand.value
    return False


def _tautology(node: ast.expr) -> bool:
    if isinstance(node, ast.Compare) and len(node.ops) == 1:
        left, right = node.left, node.comparators[0]
        same = ast.dump(left) == ast.dump(right)
        if same and isinstance(node.ops[0], ast.Eq | ast.Is | ast.GtE | ast.LtE):
            return True
        if isinstance(left, ast.Constant) and isinstance(right, ast.Constant):
            return True
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
        return any(_truthy_constant(v) for v in node.values)
    return False


def _constant_false(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and not node.value


def _call_name(node: ast.Call) -> str:
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return ""


def _is_raises(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in ("raises", "warns")
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "pytest"
    )


def _stops(stmt: ast.stmt) -> bool:
    if isinstance(stmt, ast.Return | ast.Raise):
        return True
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
        f = stmt.value.func
        return (
            isinstance(f, ast.Attribute)
            and f.attr in ("skip", "xfail", "fail", "exit")
            and isinstance(f.value, ast.Name)
            and f.value.id == "pytest"
        )
    return False


class _PyScan:
    def __init__(self, targets: set[str], helpers: dict[str, bool], source: str) -> None:
        self.targets = targets
        self.helpers = helpers
        self.source = source
        self.assertions: list[Assertion] = []
        self.calls_target = False

    def _text(self, node: ast.AST) -> str:
        text = ast.get_source_segment(self.source, node) or ast.unparse(node)
        return " ".join(text.split())[:200]

    def _calls(self, node: ast.AST) -> None:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                name = _call_name(sub)
                if name in self.targets:
                    self.calls_target = True
                if self.helpers.get(name):
                    self.assertions.append(Assertion(sub.lineno, self._text(sub)))
                if _is_raises(sub) and len(sub.args) >= 2:
                    # pytest.raises(Error, fn, *args): the call form asserts too.
                    self.assertions.append(Assertion(sub.lineno, self._text(sub)))
                if (
                    isinstance(sub.func, ast.Attribute)
                    and sub.func.attr.startswith("assert")
                    and sub.args
                    and not all(isinstance(a, ast.Constant) for a in sub.args)
                ):
                    self.assertions.append(Assertion(sub.lineno, self._text(sub)))

    def block(self, body: list[ast.stmt]) -> None:
        for stmt in body:
            if isinstance(stmt, ast.Assert):
                self._calls(stmt.test)
                if not _truthy_constant(stmt.test) and not _tautology(stmt.test):
                    self.assertions.append(Assertion(stmt.lineno, self._text(stmt)))
            elif isinstance(stmt, ast.If):
                self._calls(stmt.test)
                if not _constant_false(stmt.test):
                    self.block(stmt.body)
                self.block(stmt.orelse)
            elif isinstance(stmt, ast.While):
                if not _constant_false(stmt.test):
                    self.block(stmt.body)
            elif isinstance(stmt, ast.For | ast.AsyncFor):
                self._calls(stmt.iter)
                self.block(stmt.body)
            elif isinstance(stmt, ast.With | ast.AsyncWith):
                raises = [i for i in stmt.items if _is_raises(i.context_expr)]
                for item in stmt.items:
                    self._calls(item.context_expr)
                body_does_something = any(not isinstance(s, ast.Pass) for s in stmt.body)
                if raises and body_does_something:
                    self.assertions.append(Assertion(stmt.lineno, self._text(stmt.items[0])))
                self.block(stmt.body)
            elif isinstance(stmt, ast.Try):
                self.block(stmt.body)
                for handler in stmt.handlers:
                    self.block(handler.body)
                self.block(stmt.finalbody)
            elif isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                continue
            else:
                self._calls(stmt)
            if _stops(stmt):
                return  # nothing after this runs


def check_python(code: str, targets: set[str]) -> CheckResult:
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return _reject(
            "syntax_error", f"The test file does not parse: {exc.msg} (line {exc.lineno})"
        )
    helpers: dict[str, bool] = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("test"):
            helpers[node.name] = any(isinstance(n, ast.Assert) for n in ast.walk(node))
    functions: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith(
            "test"
        ):
            functions.append(node)
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            functions += [
                n
                for n in node.body
                if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)
                and n.name.startswith("test")
            ]
    tests: list[TestCheck] = []
    module_calls = _PyScan(targets, {}, code)
    for node in tree.body:
        if isinstance(node, ast.Assign | ast.AnnAssign | ast.Expr):
            module_calls._calls(node)  # client = TestClient(app) at module level
    for fn in functions:
        scan = _PyScan(targets, helpers, code)
        scan.block(fn.body)
        tests.append(
            TestCheck(
                fn.name,
                fn.lineno,
                scan.assertions,
                scan.calls_target or _uses_fixture(fn, module_calls),
            )
        )
    return _verdict(tests)


def _uses_fixture(fn: ast.FunctionDef | ast.AsyncFunctionDef, module: _PyScan) -> bool:
    """A module-level object built from the code under test (``client = TestClient(app)``)
    counts as the test calling it when the test uses that object."""
    return module.calls_target and any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) for n in ast.walk(fn)
    )


# ── JavaScript and TypeScript ────────────────────────────────────────────────────────

TEST_CALL = re.compile(
    r"(?<![\w$.])(?P<fn>it|test)(?P<mod>\.(?:only|concurrent|skip|todo|fails))?\s*\("
)
SKIPPED_MODS = (".skip", ".todo")
MATCHERS = (
    "toBe",
    "toEqual",
    "toStrictEqual",
    "toThrow",
    "toThrowError",
    "toMatch",
    "toMatchObject",
    "toContain",
    "toContainEqual",
    "toHaveLength",
    "toHaveProperty",
    "toBeCloseTo",
    "toBeGreaterThan",
    "toBeGreaterThanOrEqual",
    "toBeLessThan",
    "toBeLessThanOrEqual",
    "toBeTruthy",
    "toBeFalsy",
    "toBeNull",
    "toBeUndefined",
    "toBeDefined",
    "toBeNaN",
    "toBeInstanceOf",
    "toBeTypeOf",
    "toHaveBeenCalled",
    "toHaveBeenCalledWith",
    "toHaveBeenCalledTimes",
    "toSatisfy",
)
EXPECT = re.compile(r"(?<![\w$.])expect\s*\(")
ASSERT_CALL = re.compile(r"(?<![\w$])assert(?:\.\w+)?\s*\(")
LITERAL = re.compile(r"^(?:true|false|null|undefined|-?\d+(?:\.\d+)?|\"[^\"]*\"|'[^']*'|`[^`$]*`)$")
RETURN = re.compile(r"(?<![\w$])return\b")
IF_FALSE = re.compile(r"(?<![\w$])if\s*\(\s*(?:false|0)\s*\)\s*\{")


def _callback_body(masked: str, open_paren: int, close_paren: int) -> tuple[int, int] | None:
    """The (start, end) of the test callback's body inside ``it(...)``: the first arrow or
    ``function`` at the call's own bracket level (not one nested inside the body)."""
    depth = 0
    arrow = func = -1
    i = open_paren + 1
    while i < close_paren:
        ch = masked[i]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif depth == 0 and masked.startswith("=>", i):
            arrow = i
            break
        elif depth == 0 and re.match(r"function\b", masked[i : i + 9]):
            func = i
            break
        i += 1
    if arrow != -1:
        i = arrow + 2
        while i < close_paren and masked[i] in " \t\r\n":
            i += 1
        if i < close_paren and masked[i] == "{":
            end = jslex.match_close(masked, i)
            return (i + 1, end) if end != -1 else None
        return (i, close_paren)
    if func == -1:
        return None
    brace = masked.find("{", func, close_paren)
    if brace == -1:
        return None
    end = jslex.match_close(masked, brace)
    return (brace + 1, end) if end != -1 else None


def _reachable(masked: str, start: int, end: int) -> list[tuple[int, int]]:
    """Ranges of the body that can run: up to a top-level ``return`` statement, without
    ``if (false) { ... }`` blocks."""
    depths = jslex.depth_map(masked)
    base = depths[start]
    stop = end
    for m in RETURN.finditer(masked, start, end):
        if depths[m.start()] == base:
            semi = masked.find(";", m.end(), end)
            nl = masked.find("\n", m.end(), end)
            cut = min(x for x in (semi, nl, end) if x != -1)
            stop = cut
            break
    ranges = [(start, stop)]
    for m in IF_FALSE.finditer(masked, start, stop):
        close = jslex.match_close(masked, m.end() - 1)
        if close == -1:
            continue
        out = []
        for a, b in ranges:
            if m.start() >= a and close <= b:
                out += [(a, m.start()), (close + 1, b)]
            else:
                out.append((a, b))
        ranges = out
    return ranges


def _js_assertions(original: str, masked: str, a: int, b: int) -> list[Assertion]:
    found: list[Assertion] = []
    for m in EXPECT.finditer(masked, a, b):
        open_at = m.end() - 1
        close = jslex.match_close(masked, open_at)
        if close == -1 or close > b:
            continue
        subject = original[open_at + 1 : close].strip()
        chain = re.match(
            r"(?:\s*\.\s*(?:not|resolves|rejects))*\s*\.\s*(?P<matcher>\w+)\s*\(",
            masked[close + 1 : b],
        )
        if not chain or chain.group("matcher") not in MATCHERS:
            continue
        m_open = close + 1 + chain.end() - 1
        m_close = jslex.match_close(masked, m_open)
        expected = original[m_open + 1 : m_close].strip() if m_close != -1 else ""
        if LITERAL.match(subject) or (subject and subject == expected):
            continue  # expect(true).toBe(true), expect(x).toBe(x): a placeholder
        end = m_close if m_close != -1 else close
        found.append(
            Assertion(
                jslex.line_of(original, m.start()),
                " ".join(original[m.start() : end + 1].split())[:200],
            )
        )
    for m in ASSERT_CALL.finditer(masked, a, b):
        close = jslex.match_close(masked, m.end() - 1)
        args = original[m.end() : close].strip() if close != -1 else ""
        if args and not LITERAL.match(args):
            found.append(
                Assertion(
                    jslex.line_of(original, m.start()),
                    " ".join(original[m.start() : close + 1].split())[:200],
                )
            )
    return found


def check_javascript(code: str, targets: set[str]) -> CheckResult:
    masked = jslex.mask(code)
    if masked.count("{") != masked.count("}") or masked.count("(") != masked.count(")"):
        return _reject("syntax_error", "The test file has unbalanced brackets")
    target_calls = [
        re.compile(rf"(?:(?<![\w$])|\.|new\s+){re.escape(t)}\s*(?:<[^>()]*>)?\s*\(")
        for t in targets
    ]
    tests: list[TestCheck] = []
    for m in TEST_CALL.finditer(masked):
        if (m.group("mod") or "") in SKIPPED_MODS:
            continue
        open_paren = m.end() - 1
        close_paren = jslex.match_close(masked, open_paren)
        if close_paren == -1:
            continue
        title_match = re.match(r"\s*(['\"`])(.*?)\1", code[open_paren + 1 : close_paren])
        title = title_match.group(2) if title_match else m.group("fn")
        body = _callback_body(masked, open_paren, close_paren)
        check = TestCheck(title, jslex.line_of(code, m.start()))
        if body is not None:
            for a, b in _reachable(masked, *body):
                check.assertions += _js_assertions(code, masked, a, b)
                if any(p.search(masked, a, b) for p in target_calls):
                    check.calls_target = True
        tests.append(check)
    return _verdict(tests)


def check(language: str, code: str, targets: set[str]) -> CheckResult:
    if language == "python":
        return check_python(code, targets)
    return check_javascript(code, targets)
