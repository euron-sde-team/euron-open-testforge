"""Static analysis of JavaScript and TypeScript source.

Works on the lexer's masked text (``jslex.py``), so comments and strings never look like
code. Finds top-level functions (``function f()``, ``const f = () =>``,
``const f = function``), classes and their methods, and HTTP routes registered as
``app.get("/path", ...)`` or ``router.post(...)``; reads parameters and their types,
JSDoc descriptions, ``@example`` lines of the form ``call(args) // => result``, and errors
thrown under a plain ``if (condition) throw new X(...)``. Nothing is evaluated.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from testforge.analysis import jslex
from testforge.analysis.model import SOURCE_LIMIT, Example, FileResult, Param, Raise, Unit

FUNC_DECL = re.compile(
    r"(?P<export>\bexport\s+(?:default\s+)?)?(?P<async>\basync\s+)?\bfunction\s*\*?\s*"
    r"(?P<name>[A-Za-z_$][\w$]*)\s*(?:<[^>(]*>)?\s*\("
)
ARROW_DECL = re.compile(
    r"(?P<export>\bexport\s+)?\b(?:const|let|var)\s+(?P<name>[A-Za-z_$][\w$]*)\s*"
    r"(?::[^=]+)?=\s*(?P<async>async\s+)?(?:function\b\s*\*?\s*[\w$]*\s*\(|(?:<[^>(]*>)?\s*\(|"
    r"(?P<single>[A-Za-z_$][\w$]*)\s*=>)"
)
CLASS_DECL = re.compile(
    r"(?P<export>\bexport\s+(?:default\s+)?)?\b(?:abstract\s+)?class\s+(?P<name>[A-Za-z_$][\w$]*)"
)
METHOD = re.compile(
    r"(?:^|[;{}\s])(?P<mods>(?:(?:public|private|protected|static|readonly|override|async|get|set)\s+)*)"
    r"(?P<name>#?[A-Za-z_$][\w$]*)\s*(?:<[^>(]*>)?\s*\("
)
ROUTE = re.compile(r"\b(?P<owner>[A-Za-z_$][\w$]*)\.(?P<method>get|post|put|patch|delete)\(\s*")
THROW_IF = re.compile(r"\bif\s*\(")
THROW_NEW = re.compile(r"\s*\{?\s*throw\s+new\s+(?P<exc>[A-Za-z_$][\w$.]*)\s*\(")
NOT_METHODS = {
    "if",
    "for",
    "while",
    "switch",
    "catch",
    "function",
    "return",
    "constructor",
    "super",
}
EXAMPLE_LINE = re.compile(r"^(?P<expr>.+?)\s*;?\s*//\s*=>\s*(?P<expected>.+?)\s*$")
JS_TEST = re.compile(r"\.(test|spec)\.[cm]?[jt]sx?$")


def is_test_file(path: str) -> bool:
    p = PurePosixPath(path)
    return bool(JS_TEST.search(p.name)) or "__tests__" in p.parts


def module_path(path: str) -> str:
    return str(PurePosixPath(path).with_suffix(""))


def _jsdoc(original: str, masked: str, start: int) -> str:
    """The /** ... */ comment right before ``start`` (only whitespace between)."""
    j = start - 1
    while j >= 0 and original[j] in " \t\r\n":
        j -= 1
    if j < 1 or original[j - 1 : j + 1] != "*/":
        return ""
    begin = original.rfind("/**", 0, j)
    if begin == -1 or masked[begin:j].strip():
        return ""
    body = original[begin + 3 : j - 1]
    lines = [re.sub(r"^\s*\*?\s?", "", ln) for ln in body.splitlines()]
    return "\n".join(lines).strip()


def _examples(doc: str) -> list[Example]:
    out: list[Example] = []
    in_example = False
    setup: list[str] = []
    for line in doc.splitlines():
        stripped = line.strip()
        if stripped.startswith("@example"):
            in_example, setup = True, []
            rest = stripped[len("@example") :].strip()
            if not rest:
                continue
            stripped = rest
        elif stripped.startswith("@"):
            in_example = False
            continue
        if not in_example or not stripped:
            continue
        m = EXAMPLE_LINE.match(stripped)
        if m:
            out.append(
                Example(list(setup), m.group("expr").rstrip(";").strip(), m.group("expected"))
            )
        elif not stripped.startswith("//"):
            setup.append(stripped)
    return out


def _description(doc: str) -> str:
    keep = []
    for line in doc.splitlines():
        if line.strip().startswith("@"):
            break
        keep.append(line)
    return "\n".join(keep).strip()


def _params(masked: str, original: str, open_at: int, close_at: int) -> list[Param]:
    out: list[Param] = []
    for raw in jslex.split_top_level(masked, original, open_at + 1, close_at):
        text = raw.strip()
        if not text:
            continue
        kind = "positional"
        if text.startswith("..."):
            kind, text = "var", text[3:]
        default = None
        if "=" in text and not text.startswith(("{", "[")):
            text, default = (s.strip() for s in text.split("=", 1))
        name, _, annotation = text.partition(":")
        name = name.strip().rstrip("?")
        for mod in ("public ", "private ", "protected ", "readonly "):
            if name.startswith(mod):
                name = name[len(mod) :].strip()
        out.append(Param(name or text, annotation.strip(), default, kind))
    return out


def _returns(masked: str, original: str, close_at: int) -> tuple[str, int]:
    """The return annotation after ``)`` and the offset of the body (``{`` or ``=>``), or
    ``len(masked)`` when what follows is not a body (a call such as ``new Map()``)."""
    i = close_at + 1
    n = len(masked)
    while i < n and masked[i] in " \t\r\n":
        i += 1
    if masked.startswith("=>", i) or (i < n and masked[i] == "{"):
        return "", i
    if i >= n or masked[i] != ":":
        return "", n
    # A return type: it may itself contain braces ({ ok: boolean }), so the body is the
    # first "{" that does not continue the type (after ":", "|", "&", ",", "<" or "(").
    j = i + 1
    depth = 0
    prev = ":"
    while j < n:
        ch = masked[j]
        if masked.startswith("=>", j) and depth == 0:
            return " ".join(original[i + 1 : j].split()), j
        if ch in "([<":
            depth += 1
        elif ch in ")]>":
            depth -= 1
        elif ch == "{":
            if depth == 0 and prev not in ":|&,<(=":
                return " ".join(original[i + 1 : j].split()), j
            close = jslex.match_close(masked, j)
            if close == -1:
                return "", n
            j = close
            prev = "}"
            j += 1
            continue
        elif ch in ";" and depth == 0:
            return "", n
        if ch not in " \t\r\n":
            prev = ch
        j += 1
    return "", n


def _body_end(masked: str, body_start: int) -> int:
    if body_start >= len(masked):
        return len(masked) - 1
    if masked[body_start] == "{":
        end = jslex.match_close(masked, body_start)
        return end if end != -1 else len(masked) - 1
    # An arrow with an expression body: up to the end of the statement.
    i = body_start + 2
    while i < len(masked) and masked[i] in " \t\r\n":
        i += 1
    if i < len(masked) and masked[i] == "{":
        end = jslex.match_close(masked, i)
        return end if end != -1 else len(masked) - 1
    depth = 0
    for j in range(i, len(masked)):
        ch = masked[j]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            if depth == 0:
                return j - 1
            depth -= 1
        elif ch in ";\n" and depth == 0:
            return j
    return len(masked) - 1


def _raises(original: str, masked: str, start: int, end: int) -> list[Raise]:
    out: list[Raise] = []
    for m in THROW_IF.finditer(masked, start, end):
        open_at = m.end() - 1
        close_at = jslex.match_close(masked, open_at)
        if close_at == -1 or close_at > end:
            continue
        throw = THROW_NEW.match(masked, close_at + 1)
        if not throw:
            continue
        exc = throw.group("exc")
        call_open = throw.end() - 1
        call_close = jslex.match_close(masked, call_open)
        message = ""
        if call_close != -1:
            arg = original[call_open + 1 : call_close].strip()
            if len(arg) >= 2 and arg[0] in "'\"`" and arg[-1] == arg[0]:
                message = arg[1:-1]
        out.append(
            Raise(
                exc,
                " ".join(original[open_at + 1 : close_at].split()),
                message,
                jslex.line_of(original, throw.start("exc")),
            )
        )
    return out


def _statement_lines(original: str, masked: str, start: int, end: int) -> list[int]:
    first = jslex.line_of(original, start)
    lines = masked[start : end + 1].splitlines()
    out = []
    for i, line in enumerate(lines):
        code = line.strip()
        if i == 0:
            continue  # the declaration line
        if code and code not in ("{", "}", "};", "});", ")", ");", "]", "];"):
            out.append(first + i)
    return out


def _segment(original: str, start: int, end: int) -> str:
    text = original[start : end + 1]
    return text if len(text) <= SOURCE_LIMIT else text[: SOURCE_LIMIT - 4] + "\n..."


def _string_at(original: str, i: int) -> str | None:
    if i >= len(original) or original[i] not in "'\"`":
        return None
    q = original[i]
    j = original.find(q, i + 1)
    return original[i + 1 : j] if j != -1 else None


def analyze(path: str, text: str) -> FileResult:
    result = FileResult()
    language = "typescript" if path.endswith((".ts", ".tsx", ".mts", ".cts")) else "javascript"
    masked = jslex.mask(text)
    depths = jslex.depth_map(masked)
    module = module_path(path)

    for m in re.finditer(r"""(?:from|require\(|import\()\s*['"]([^'"]+)['"]""", text):
        if masked[m.start()] != " ":
            spec = m.group(1)
            if not spec.startswith("."):
                parts = spec.split("/")
                result.imports.add("/".join(parts[:2]) if spec.startswith("@") else parts[0])

    def add_function(
        name: str, decl_start: int, paren_open: int, exported: bool, is_async: bool
    ) -> None:
        paren_close = jslex.match_close(masked, paren_open)
        if paren_close == -1:
            return
        returns, body_start = _returns(masked, text, paren_close)
        end = _body_end(masked, body_start)
        doc = _jsdoc(text, masked, decl_start)
        result.units.append(
            Unit(
                kind="function",
                language=language,
                name=name,
                qualname=f"{module}.{name}",
                file=path,
                module=module,
                start_line=jslex.line_of(text, decl_start),
                end_line=jslex.line_of(text, end),
                signature=" ".join(text[decl_start:body_start].split()).rstrip("{ ").rstrip(),
                docstring=_description(doc),
                source=_segment(text, decl_start, end),
                params=_params(masked, text, paren_open, paren_close),
                returns=returns,
                examples=_examples(doc),
                raises=_raises(text, masked, body_start, end),
                exported=exported,
                is_async=is_async,
                statement_lines=_statement_lines(text, masked, decl_start, end),
            )
        )

    for m in FUNC_DECL.finditer(masked):
        if depths[m.start()] != 0:
            continue
        start = m.start("export") if m.group("export") else m.start()
        add_function(
            m.group("name"), start, m.end() - 1, bool(m.group("export")), bool(m.group("async"))
        )

    for m in ARROW_DECL.finditer(masked):
        if depths[m.start()] != 0:
            continue
        start = m.start("export") if m.group("export") else m.start()
        if m.group("single"):
            # x => ...: a single bare parameter.
            name_at = m.start("single")
            end = _body_end(masked, masked.find("=>", name_at))
            doc = _jsdoc(text, masked, start)
            result.units.append(
                Unit(
                    kind="function",
                    language=language,
                    name=m.group("name"),
                    qualname=f"{module}.{m.group('name')}",
                    file=path,
                    module=module,
                    start_line=jslex.line_of(text, start),
                    end_line=jslex.line_of(text, end),
                    signature=" ".join(text[start : masked.find("=>", name_at) + 2].split()),
                    docstring=_description(doc),
                    source=_segment(text, start, end),
                    params=[Param(m.group("single"))],
                    examples=_examples(doc),
                    raises=_raises(text, masked, name_at, end),
                    exported=bool(m.group("export")),
                    is_async=bool(m.group("async")),
                    statement_lines=_statement_lines(text, masked, start, end),
                )
            )
            continue
        add_function(
            m.group("name"), start, m.end() - 1, bool(m.group("export")), bool(m.group("async"))
        )

    for m in CLASS_DECL.finditer(masked):
        if depths[m.start()] != 0:
            continue
        start = m.start("export") if m.group("export") else m.start()
        open_at = masked.find("{", m.end())
        if open_at == -1:
            continue
        close_at = jslex.match_close(masked, open_at)
        if close_at == -1:
            continue
        cls = m.group("name")
        doc = _jsdoc(text, masked, start)
        cls_unit = Unit(
            kind="class",
            language=language,
            name=cls,
            qualname=f"{module}.{cls}",
            file=path,
            module=module,
            start_line=jslex.line_of(text, start),
            end_line=jslex.line_of(text, close_at),
            signature=" ".join(text[start:open_at].split()),
            docstring=_description(doc),
            source=_segment(text, start, close_at),
            examples=_examples(doc),
            exported=bool(m.group("export")),
        )
        result.units.append(cls_unit)
        class_depth = depths[open_at] + 1
        for mm in METHOD.finditer(masked, open_at + 1, close_at):
            name_at = mm.start("name")
            if depths[name_at] != class_depth:
                continue
            name = mm.group("name")
            paren_open = mm.end() - 1
            paren_close = jslex.match_close(masked, paren_open)
            if paren_close == -1:
                continue
            returns, body_start = _returns(masked, text, paren_close)
            if body_start >= len(masked) or masked[body_start] != "{":
                continue
            end = _body_end(masked, body_start)
            mods = mm.group("mods") or ""
            decl_start = mm.start("mods") if mods else name_at
            mdoc = _jsdoc(text, masked, decl_start)
            if name == "constructor":
                cls_unit.params = _params(masked, text, paren_open, paren_close)
                cls_unit.raises = _raises(text, masked, body_start, end)
                continue
            if name in NOT_METHODS:
                continue
            result.units.append(
                Unit(
                    kind="method",
                    language=language,
                    name=name,
                    qualname=f"{module}.{cls}.{name}",
                    file=path,
                    module=module,
                    start_line=jslex.line_of(text, decl_start),
                    end_line=jslex.line_of(text, end),
                    signature=" ".join(text[decl_start:body_start].split()),
                    docstring=_description(mdoc),
                    source=_segment(text, decl_start, end),
                    params=_params(masked, text, paren_open, paren_close),
                    returns=returns,
                    examples=_examples(mdoc) or _examples(doc),
                    raises=_raises(text, masked, body_start, end),
                    exported=cls_unit.exported
                    and not name.startswith("#")
                    and "private" not in mods,
                    is_async="async" in mods,
                    statement_lines=_statement_lines(text, masked, decl_start, end),
                    class_name=cls,
                )
            )

    for m in ROUTE.finditer(masked):
        path_text = _string_at(text, m.end())
        if path_text is None or not path_text.startswith("/"):
            continue
        method = m.group("method").upper()
        call_open = m.end() - 1
        while call_open > 0 and masked[call_open] != "(":
            call_open -= 1
        call_close = jslex.match_close(masked, call_open)
        end = call_close if call_close != -1 else m.end()
        result.units.append(
            Unit(
                kind="route",
                language=language,
                name=f"{method.lower()} {path_text}",
                qualname=f"{method} {path_text}",
                file=path,
                module=module,
                start_line=jslex.line_of(text, m.start()),
                end_line=jslex.line_of(text, end),
                signature=" ".join(text[m.start() : min(end + 1, m.start() + 160)].split())[:200],
                source=_segment(text, m.start(), end),
                route_method=method,
                route_path=path_text,
                statement_lines=_statement_lines(text, masked, m.start(), end),
            )
        )
    result.units.sort(key=lambda u: u.start_line)
    return result
