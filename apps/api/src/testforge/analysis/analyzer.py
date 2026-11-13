"""Analyze a whole snapshot: languages, frameworks, test frameworks, code units, existing
test files and which units no test refers to.

Input is the snapshot's text files (path -> text); nothing is executed or imported.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import PurePosixPath

from testforge.analysis import javascript, python
from testforge.analysis.model import (
    JS_EXTENSIONS,
    PY_EXTENSIONS,
    TS_EXTENSIONS,
    Analysis,
    AppEntry,
    Unit,
)

PY_FRAMEWORKS = {"fastapi": "fastapi", "flask": "flask", "django": "django"}
JS_FRAMEWORKS = {
    "express": "express",
    "fastify": "fastify",
    "koa": "koa",
    "react": "react",
    "next": "next",
    "vue": "vue",
}
JS_TEST_FRAMEWORKS = ("vitest", "jest", "mocha")
_REQ_NAME = re.compile(r"^\s*([A-Za-z0-9_.\-]+)")
_IDENT = re.compile(r"[A-Za-z_$][\w$]*")


def language_of(path: str) -> str | None:
    if path.endswith(PY_EXTENSIONS):
        return "python"
    if path.endswith(TS_EXTENSIONS):
        return "typescript"
    if path.endswith(JS_EXTENSIONS):
        return "javascript"
    return None


def _python_deps(files: dict[str, str]) -> list[str]:
    deps: set[str] = set()
    for path, text in files.items():
        name = PurePosixPath(path).name
        if name.startswith("requirements") and name.endswith(".txt"):
            for line in text.splitlines():
                line = line.strip()
                if line and not line.startswith(("#", "-")):
                    m = _REQ_NAME.match(line)
                    if m:
                        deps.add(m.group(1).lower())
        elif name == "pyproject.toml":
            try:
                data = tomllib.loads(text)
            except tomllib.TOMLDecodeError:
                continue
            project = data.get("project", {})
            groups = [project.get("dependencies", [])]
            groups += list(project.get("optional-dependencies", {}).values())
            groups += list(data.get("dependency-groups", {}).values())
            for group in groups:
                for spec in group:
                    if isinstance(spec, str):
                        m = _REQ_NAME.match(spec)
                        if m:
                            deps.add(m.group(1).lower())
    return sorted(deps)


def _js_deps(files: dict[str, str]) -> list[str]:
    deps: set[str] = set()
    for path, text in files.items():
        if PurePosixPath(path).name != "package.json" or "node_modules" in path:
            continue
        try:
            data = json.loads(text)
        except ValueError:
            continue
        if not isinstance(data, dict):
            continue
        for key in ("dependencies", "devDependencies", "peerDependencies"):
            section = data.get(key)
            if isinstance(section, dict):
                deps.update(str(k) for k in section)
    return sorted(deps)


def _referenced(units: list[Unit], test_texts: list[str]) -> set[str]:
    """Qualnames of units whose name appears as an identifier in any test file."""
    idents: set[str] = set()
    for text in test_texts:
        idents.update(_IDENT.findall(text))
    out = set()
    for u in units:
        if u.kind == "route":
            if u.route_path and any(u.route_path in t for t in test_texts):
                out.add(u.qualname)
        elif u.name in idents:
            out.add(u.qualname)
    return out


def analyze(files: dict[str, str]) -> tuple[Analysis, set[str]]:
    """The analysis and the qualnames some existing test refers to."""
    units: list[Unit] = []
    languages: set[str] = set()
    imports: set[str] = set()
    apps: list[AppEntry] = []
    tests: list[str] = []
    sources: list[str] = []
    errors: dict[str, str] = {}
    skipped: list[str] = []
    test_texts: list[str] = []
    for path in sorted(files):
        language = language_of(path)
        if language is None:
            continue
        languages.add(language)
        text = files[path]
        if language == "python":
            if python.is_test_file(path):
                tests.append(path)
                test_texts.append(text)
                if "import pytest" in text or "from pytest" in text:
                    imports.add("pytest")
                if "unittest" in text:
                    imports.add("unittest")
                continue
            result = python.analyze(path, text)
        else:
            if javascript.is_test_file(path):
                tests.append(path)
                test_texts.append(text)
                for fw in JS_TEST_FRAMEWORKS:
                    if f"'{fw}'" in text or f'"{fw}"' in text:
                        imports.add(fw)
                continue
            if path.endswith(".d.ts") or ".config." in PurePosixPath(path).name:
                skipped.append(path)
                continue
            result = javascript.analyze(path, text)
        sources.append(path)
        if result.parse_error:
            errors[path] = result.parse_error
        units.extend(result.units)
        imports.update(result.imports)
        apps.extend(result.apps)

    py_deps = _python_deps(files)
    js_deps = _js_deps(files)
    names = imports | set(py_deps) | set(js_deps)
    frameworks = sorted(
        {fw for key, fw in PY_FRAMEWORKS.items() if key in names}
        | {fw for key, fw in JS_FRAMEWORKS.items() if key in names}
    )
    test_frameworks: set[str] = set()
    if "python" in languages and (
        "pytest" in names or any(PurePosixPath(t).name == "conftest.py" for t in tests)
    ):
        test_frameworks.add("pytest")
    elif "python" in languages and "unittest" in names:
        test_frameworks.add("unittest")
    test_frameworks.update(fw for fw in JS_TEST_FRAMEWORKS if fw in names)
    analysis = Analysis(
        languages=sorted(languages),
        frameworks=frameworks,
        test_frameworks=sorted(test_frameworks),
        units=units,
        test_files=tests,
        source_files=sources,
        dependencies={"python": py_deps, "javascript": js_deps},
        apps=apps,
        parse_errors=errors,
        skipped=skipped,
    )
    return analysis, _referenced(units, test_texts)
