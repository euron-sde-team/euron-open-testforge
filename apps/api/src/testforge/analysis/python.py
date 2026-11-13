"""Static analysis of Python source with the standard library's ``ast``.

Finds module-level functions, classes and their methods, and HTTP routes declared with
FastAPI (``@app.get``, ``@router.post``, ``APIRouter(prefix=...)``) or Flask
(``@app.route``, ``@bp.get``) decorators; reads each one's parameters, return annotation,
docstring, documented examples (doctests), the errors it raises and the condition that
leads to each, and the statement lines a test could execute. Nothing is imported or run.
"""

from __future__ import annotations

import ast
import doctest
from pathlib import PurePosixPath

from testforge.analysis.model import SOURCE_LIMIT, AppEntry, Example, FileResult, Param, Raise, Unit

HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")


def module_name(path: str) -> str:
    """``app/pricing.py`` -> ``app.pricing``; ``src/shop/cart.py`` -> ``shop.cart`` (the
    sandbox puts both the workspace and ``src/`` on the import path)."""
    parts = list(PurePosixPath(path).with_suffix("").parts)
    if parts and parts[0] == "src" and len(parts) > 1:
        parts = parts[1:]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def is_test_file(path: str) -> bool:
    p = PurePosixPath(path)
    return (
        p.name.startswith("test_")
        or p.name.endswith("_test.py")
        or p.name == "conftest.py"
        or "tests" in p.parts[:-1]
        or "test" in p.parts[:-1]
    )


def _unparse(node: ast.AST | None) -> str:
    return ast.unparse(node) if node is not None else ""


def _params(args: ast.arguments, *, skip_self: bool) -> list[Param]:
    out: list[Param] = []
    positional = [*args.posonlyargs, *args.args]
    defaults: list[ast.expr | None] = [None] * (len(positional) - len(args.defaults))
    defaults += list(args.defaults)
    for i, (arg, default) in enumerate(zip(positional, defaults, strict=True)):
        if skip_self and i == 0 and arg.arg in ("self", "cls"):
            continue
        out.append(
            Param(
                arg.arg,
                _unparse(arg.annotation),
                _unparse(default) if default is not None else None,
            )
        )
    if args.vararg:
        out.append(Param(args.vararg.arg, _unparse(args.vararg.annotation), None, "var"))
    for arg, kw_default in zip(args.kwonlyargs, args.kw_defaults, strict=True):
        out.append(
            Param(
                arg.arg,
                _unparse(arg.annotation),
                _unparse(kw_default) if kw_default is not None else None,
                "keyword",
            )
        )
    if args.kwarg:
        out.append(Param(args.kwarg.arg, _unparse(args.kwarg.annotation), None, "varkw"))
    return out


def _examples(docstring: str) -> list[Example]:
    """Doctests as (setup, expression, expected): lines with no output are setup for the
    next line that has one."""
    try:
        parsed = doctest.DocTestParser().get_examples(docstring)
    except ValueError:
        return []
    out: list[Example] = []
    setup: list[str] = []
    for ex in parsed:
        source = ex.source.strip()
        want = ex.want.strip()
        if not want:
            setup.append(source)
            continue
        if "Traceback" in want:
            setup = []
            continue
        out.append(Example(list(setup), source, want))
    return out


def _raise_name(node: ast.Raise) -> tuple[str, str]:
    exc = node.exc
    if exc is None:
        return "", ""
    call = exc if isinstance(exc, ast.Call) else None
    target = call.func if call is not None else exc
    name = _unparse(target)
    message = ""
    if call is not None and call.args and isinstance(call.args[0], ast.Constant):
        message = str(call.args[0].value)
    return name, message


def _raises(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> list[Raise]:
    out: list[Raise] = []
    seen: set[int] = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.If):
            for stmt in node.body:
                if isinstance(stmt, ast.Raise) and id(stmt) not in seen:
                    seen.add(id(stmt))
                    name, message = _raise_name(stmt)
                    if name:
                        out.append(Raise(name, _unparse(node.test), message, stmt.lineno))
    for node in ast.walk(fn):
        if isinstance(node, ast.Raise) and id(node) not in seen:
            name, message = _raise_name(node)
            if name:
                out.append(Raise(name, None, message, node.lineno))
    return out


def _statement_lines(fn: ast.AST) -> list[int]:
    body = getattr(fn, "body", [])
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]  # the docstring is not a statement a test executes
    lines: set[int] = set()
    for stmt in body:
        for node in ast.walk(stmt):
            if isinstance(node, ast.stmt) and not isinstance(
                node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
            ):
                lines.add(node.lineno)
    return sorted(lines)


def _signature(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    prefix = "async def" if isinstance(fn, ast.AsyncFunctionDef) else "def"
    returns = f" -> {_unparse(fn.returns)}" if fn.returns is not None else ""
    return f"{prefix} {fn.name}({_unparse(fn.args)}){returns}"


def _segment(lines: list[str], node: ast.AST) -> str:
    start = getattr(node, "lineno", 1)
    decorators = getattr(node, "decorator_list", [])
    if decorators:
        start = min(start, *(d.lineno for d in decorators))
    end = getattr(node, "end_lineno", start) or start
    text = "\n".join(lines[start - 1 : end])
    return text if len(text) <= SOURCE_LIMIT else text[: SOURCE_LIMIT - 4] + "\n..."


def _route(dec: ast.expr, prefixes: dict[str, str]) -> tuple[str, str] | None:
    """(METHOD, path) for a FastAPI or Flask route decorator."""
    if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
        return None
    attr = dec.func.attr
    owner = _unparse(dec.func.value)
    path_arg = dec.args[0] if dec.args else None
    if not isinstance(path_arg, ast.Constant) or not isinstance(path_arg.value, str):
        return None
    path = prefixes.get(owner, "") + path_arg.value
    if attr in HTTP_METHODS:
        return attr.upper(), path or "/"
    if attr == "route":
        methods = ["GET"]
        for kw in dec.keywords:
            if kw.arg == "methods" and isinstance(kw.value, ast.List | ast.Tuple):
                methods = [
                    str(e.value).upper()
                    for e in kw.value.elts
                    if isinstance(e, ast.Constant) and isinstance(e.value, str)
                ]
        return (methods[0] if methods else "GET"), path or "/"
    return None


def _app_objects(tree: ast.Module, module: str, path: str) -> tuple[list[AppEntry], dict[str, str]]:
    """Application objects (``app = FastAPI()``, ``app = Flask(__name__)``) and router
    prefixes (``router = APIRouter(prefix="/items")``) assigned at module level."""
    apps: list[AppEntry] = []
    prefixes: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        ctor = _unparse(node.value.func).rsplit(".", 1)[-1]
        names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if not names:
            continue
        if ctor in ("FastAPI", "Flask"):
            apps.append(AppEntry(ctor.lower(), module, names[0], path))
        if ctor in ("APIRouter", "Blueprint"):
            for kw in node.value.keywords:
                if kw.arg in ("prefix", "url_prefix") and isinstance(kw.value, ast.Constant):
                    prefixes[names[0]] = str(kw.value.value)
    return apps, prefixes


def analyze(path: str, text: str) -> FileResult:
    result = FileResult()
    try:
        tree = ast.parse(text, filename=path)
    except (SyntaxError, ValueError) as exc:
        result.parse_error = f"{exc.__class__.__name__}: {exc}"
        return result
    lines = text.splitlines()
    module = module_name(path)
    apps, prefixes = _app_objects(tree, module, path)
    result.apps = apps

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.imports.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            result.imports.add(node.module.split(".")[0])

    def function_unit(fn: ast.FunctionDef | ast.AsyncFunctionDef, cls: ast.ClassDef | None) -> Unit:
        doc = ast.get_docstring(fn) or ""
        qual = f"{module}.{cls.name}.{fn.name}" if cls else f"{module}.{fn.name}"
        unit = Unit(
            kind="method" if cls else "function",
            language="python",
            name=fn.name,
            qualname=qual,
            file=path,
            module=module,
            start_line=fn.lineno,
            end_line=fn.end_lineno or fn.lineno,
            signature=_signature(fn),
            docstring=doc,
            source=_segment(lines, fn),
            params=_params(fn.args, skip_self=cls is not None),
            returns=_unparse(fn.returns),
            examples=_examples(doc),
            raises=_raises(fn),
            exported=not fn.name.startswith("_") or fn.name == "__init__",
            is_async=isinstance(fn, ast.AsyncFunctionDef),
            statement_lines=_statement_lines(fn),
            class_name=cls.name if cls else None,
        )
        for dec in fn.decorator_list:
            route = _route(dec, prefixes)
            if route:
                unit.kind = "route"
                unit.route_method, unit.route_path = route
                unit.qualname = f"{route[0]} {route[1]}"
                break
        return unit

    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            result.units.append(function_unit(node, None))
        elif isinstance(node, ast.ClassDef):
            doc = ast.get_docstring(node) or ""
            examples = _examples(doc)
            cls_unit = Unit(
                kind="class",
                language="python",
                name=node.name,
                qualname=f"{module}.{node.name}",
                file=path,
                module=module,
                start_line=node.lineno,
                end_line=node.end_lineno or node.lineno,
                signature=f"class {node.name}"
                + (f"({', '.join(_unparse(b) for b in node.bases)})" if node.bases else ""),
                docstring=doc,
                source=_segment(lines, node),
                examples=examples,
                exported=not node.name.startswith("_"),
            )
            result.units.append(cls_unit)
            for item in node.body:
                if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
                    if item.name.startswith("__") and item.name != "__init__":
                        continue
                    method = function_unit(item, node)
                    if item.name == "__init__":
                        cls_unit.params = method.params
                        cls_unit.raises = method.raises
                        cls_unit.statement_lines = method.statement_lines
                        continue
                    result.units.append(method)
    return result
