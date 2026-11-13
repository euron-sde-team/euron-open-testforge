"""Explain a failed test from what the same run captured (A8).

The runner plugins record, at the moment an assertion fails, the operator and both
operands (pytest's ``pytest_assertrepr_compare``, Vitest's ``TestError.actual`` and
``expected``), the failing line, and the error. This turns them into a plain explanation:
which assertion failed, what the code returned, what the test expected, and where. The
test is never run a second time to get it.
"""

from __future__ import annotations

import ast
import re
from typing import Any

OPERATOR_WORDS = {
    "==": "to equal",
    "!=": "to differ from",
    "<": "to be less than",
    "<=": "to be at most",
    ">": "to be greater than",
    ">=": "to be at least",
    "in": "to be in",
    "not in": "not to be in",
    "is": "to be",
    "is not": "not to be",
    "toBe": "to be",
    "toEqual": "to equal",
    "toStrictEqual": "to equal",
}
NETWORK_MARKERS = (
    "Network is unreachable",
    "Temporary failure in name resolution",
    "Name or service not known",
    "ENETUNREACH",
    "EAI_AGAIN",
    "ENOTFOUND",
)
RAISES = re.compile(r"DID NOT RAISE <class '([\w.]+)'>")
JS_THROW = re.compile(r"expected \[Function.*?\] to throw", re.IGNORECASE)


def _diff_hint(actual: str, expected: str) -> str:
    """A short, concrete hint for common value differences."""
    try:
        a, e = ast.literal_eval(actual), ast.literal_eval(expected)
    except (ValueError, SyntaxError, MemoryError, RecursionError):
        return ""
    if isinstance(a, list) and isinstance(e, list):
        if len(a) != len(e):
            return f" The result has {len(a)} items where {len(e)} were expected."
        diffs = [i for i, (x, y) in enumerate(zip(a, e, strict=True)) if x != y]
        if diffs:
            i = diffs[0]
            hint = f" They first differ at index {i}: {a[i]!r} instead of {e[i]!r}."
            if all(isinstance(v, int | float) for v in (*a, *e)):
                sa, se = round(sum(a), 6), round(sum(e), 6)
                if sa != se:
                    hint += f" The items add up to {sa} instead of {se}."
            return hint
    if isinstance(a, int | float) and isinstance(e, int | float) and not isinstance(a, bool):
        delta = round(float(a) - float(e), 6)
        return f" The difference is {delta:+g}."
    if isinstance(a, dict) and isinstance(e, dict):
        missing = sorted(set(e) - set(a))
        extra = sorted(set(a) - set(e))
        changed = sorted(k for k in set(a) & set(e) if a[k] != e[k])
        parts = []
        if missing:
            parts.append(f"missing keys {missing}")
        if extra:
            parts.append(f"unexpected keys {extra}")
        if changed:
            parts.append(f"different values for {changed}")
        return (" It has " + ", ".join(parts) + ".") if parts else ""
    return ""


def explain(case: dict[str, Any], source_line: str | None = None) -> dict[str, Any]:
    """The structured failure (``kind``, ``actual``, ``expected``, ``operator``, ``line``,
    ``expression``) and its ``explanation`` in plain words."""
    failure = case.get("failure") or {}
    name = case.get("name") or case.get("nodeid") or "The test"
    where = str(failure.get("path") or case.get("file") or "").removeprefix("/box/")
    line = failure.get("line")
    location = f" at {where}:{line}" if where and line else ""
    compare = failure.get("compare") or {}
    message = str(failure.get("message") or "").strip()
    out: dict[str, Any] = {
        "kind": "error",
        "operator": None,
        "actual": None,
        "expected": None,
        "line": line,
        "expression": (source_line or "").strip() or None,
        "message": message[:2000],
    }
    if compare:
        op = str(compare.get("operator") or "==")
        actual, expected = str(compare.get("left")), str(compare.get("right"))
        out |= {"kind": "assertion", "operator": op, "actual": actual, "expected": expected}
        words = OPERATOR_WORDS.get(op, f"to satisfy {op} against")
        expr = f" (`{out['expression']}`)" if out["expression"] else ""
        out["explanation"] = (
            f"{name} failed{location}: the assertion{expr} expected the value {words} "
            f"{expected}, but the code returned {actual}.{_diff_hint(actual, expected)}"
            " Nothing else in the test failed; this one comparison decides it."
        )
        return out
    raised = RAISES.search(message)
    if raised or JS_THROW.search(message):
        exc = raised.group(1) if raised else "an error"
        out |= {"kind": "no_exception", "expected": exc, "actual": "returned normally"}
        out["explanation"] = (
            f"{name} failed{location}: it expected the call to raise {exc}, but the call "
            "returned normally. The input does not trigger the error the code is supposed "
            "to raise for it."
        )
        return out
    if message.startswith(("AssertionError", "assert ")) or "AssertionError" in message:
        out["kind"] = "assertion"
        out["explanation"] = f"{name} failed{location}: {message.splitlines()[0][:400]}"
        return out
    first = message.splitlines()[0][:400] if message else "an error"
    if any(marker in message for marker in NETWORK_MARKERS):
        out["kind"] = "refused"
        out["explanation"] = (
            f"{name} tried to open a network connection{location} and the sandbox refused it: "
            f"{first}. Runs have no network; a test that needs a service should use a fake or "
            "drive the app in process."
        )
        return out
    if "No such file or directory" in message and "/box/" not in message.split("No such file")[-1]:
        out["kind"] = "refused"
        out["explanation"] = (
            f"{name} tried to read a file outside its workspace{location}, which the sandbox "
            f"does not have: {first}. A run sees only its own project's files."
        )
        return out
    out["explanation"] = (
        f"{name} stopped with an error{location} before it could check anything: {first}. "
        "This is the code (or the test's setup) raising, not an assertion failing."
    )
    return out
