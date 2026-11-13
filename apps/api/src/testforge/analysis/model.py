"""What static analysis produces, independent of the database.

Analysis reads source text only. It never imports, evaluates or executes the code it
analyzes: Python is parsed with the standard library's ``ast``, JavaScript and TypeScript
with a small lexer (``javascript.py``). Executing anything happens later, in the sandbox.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

PY_EXTENSIONS = (".py",)
JS_EXTENSIONS = (".js", ".mjs", ".cjs", ".jsx")
TS_EXTENSIONS = (".ts", ".mts", ".cts", ".tsx")
SOURCE_LIMIT = 8_000


@dataclass
class Param:
    name: str
    annotation: str = ""
    default: str | None = None
    kind: str = "positional"

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "annotation": self.annotation,
            "default": self.default,
            "kind": self.kind,
        }


@dataclass
class Example:
    """A documented call and its documented result (a doctest, a JSDoc @example)."""

    # Statements to run first (setup lines without an output), then the expression.
    setup: list[str]
    expression: str
    expected: str

    def as_dict(self) -> dict[str, Any]:
        return {"setup": self.setup, "expression": self.expression, "expected": self.expected}


@dataclass
class Raise:
    """An error the unit raises, and the condition that leads to it when it is a plain
    ``if <condition>: raise X(...)``."""

    exception: str
    condition: str | None
    message: str
    line: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "exception": self.exception,
            "condition": self.condition,
            "message": self.message,
            "line": self.line,
        }


@dataclass
class Unit:
    kind: str  # function, method, class, route
    language: str
    name: str
    qualname: str
    file: str
    module: str
    start_line: int
    end_line: int
    signature: str = ""
    docstring: str = ""
    source: str = ""
    params: list[Param] = field(default_factory=list)
    returns: str = ""
    examples: list[Example] = field(default_factory=list)
    raises: list[Raise] = field(default_factory=list)
    exported: bool = True
    is_async: bool = False
    statement_lines: list[int] = field(default_factory=list)
    class_name: str | None = None
    route_method: str | None = None
    route_path: str | None = None
    # For methods: how the class is built in its own documented examples, if anywhere.
    constructor: str | None = None

    def details(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "params": [p.as_dict() for p in self.params],
            "returns": self.returns,
            "examples": [e.as_dict() for e in self.examples],
            "raises": [r.as_dict() for r in self.raises],
            "statement_lines": self.statement_lines,
        }
        if self.class_name:
            out["class_name"] = self.class_name
        if self.route_method:
            out["route"] = {"method": self.route_method, "path": self.route_path}
        if self.constructor:
            out["constructor"] = self.constructor
        return out


@dataclass
class AppEntry:
    """An application object API tests can drive in process (no network)."""

    framework: str  # fastapi, flask
    module: str
    attr: str
    file: str

    def as_dict(self) -> dict[str, str]:
        return {
            "framework": self.framework,
            "module": self.module,
            "attr": self.attr,
            "file": self.file,
        }


@dataclass
class FileResult:
    units: list[Unit] = field(default_factory=list)
    imports: set[str] = field(default_factory=set)
    apps: list[AppEntry] = field(default_factory=list)
    parse_error: str | None = None


@dataclass
class Analysis:
    languages: list[str]
    frameworks: list[str]
    test_frameworks: list[str]
    units: list[Unit]
    test_files: list[str]
    source_files: list[str]
    dependencies: dict[str, list[str]]
    apps: list[AppEntry]
    parse_errors: dict[str, str]
    skipped: list[str]

    def summary(self) -> dict[str, Any]:
        kinds: dict[str, int] = {}
        for u in self.units:
            kinds[u.kind] = kinds.get(u.kind, 0) + 1
        return {
            "units": len(self.units),
            "by_kind": kinds,
            "source_files": len(self.source_files),
            "test_files": self.test_files[:500],
            "test_file_count": len(self.test_files),
            "dependencies": self.dependencies,
            "apps": [a.as_dict() for a in self.apps],
            "parse_errors": dict(list(self.parse_errors.items())[:50]),
            "skipped": self.skipped[:200],
        }
