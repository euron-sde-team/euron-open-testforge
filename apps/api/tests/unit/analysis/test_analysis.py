"""Static analysis of Python and TypeScript, on fixtures and the demo projects (A6)."""

from __future__ import annotations

from pathlib import Path

from testforge.analysis import analyzer, javascript, jslex, python

DEMO = Path(__file__).parents[3] / "src" / "testforge" / "demo" / "projects"


def _files(name: str) -> dict[str, str]:
    root = DEMO / name
    return {
        str(p.relative_to(root)): p.read_text()
        for p in root.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    }


def test_python_module_names() -> None:
    assert python.module_name("app/pricing.py") == "app.pricing"
    assert python.module_name("src/shop/cart.py") == "shop.cart"
    assert python.module_name("pkg/__init__.py") == "pkg"
    assert python.is_test_file("tests/test_a.py") and python.is_test_file("a_test.py")
    assert not python.is_test_file("app/main.py")


def test_python_functions_examples_raises_and_routes() -> None:
    src = '''
from fastapi import APIRouter, FastAPI

app = FastAPI()
router = APIRouter(prefix="/items")


def total(prices: list[float], tax: float = 0.1, *, rounding: int = 2) -> float:
    """Sum with tax.

    >>> total([1.0, 2.0])
    3.3
    """
    if tax < 0:
        raise ValueError("tax must not be negative")
    return round(sum(prices) * (1 + tax), rounding)


async def fetch(url):
    raise NotImplementedError


@router.get("/{item_id}")
def get_item(item_id: int):
    return {"id": item_id}


@app.route("/legacy", methods=["POST"])
def legacy():
    return "ok"


class Box:
    """A box.

    >>> b = Box(3)
    >>> b.size()
    3
    """

    def __init__(self, n: int) -> None:
        if n < 0:
            raise ValueError("no")
        self.n = n

    def size(self) -> int:
        return self.n

    def _hidden(self) -> None:
        pass

    def __repr__(self) -> str:
        return "Box"
'''
    result = python.analyze("app/things.py", src)
    by = {u.qualname: u for u in result.units}
    t = by["app.things.total"]
    assert t.kind == "function" and t.returns == "float"
    assert [(p.name, p.annotation, p.default, p.kind) for p in t.params] == [
        ("prices", "list[float]", None, "positional"),
        ("tax", "float", "0.1", "positional"),
        ("rounding", "int", "2", "keyword"),
    ]
    assert t.examples[0].expression == "total([1.0, 2.0])" and t.examples[0].expected == "3.3"
    assert t.raises[0].condition == "tax < 0" and t.raises[0].message == "tax must not be negative"
    assert t.statement_lines  # the docstring is not one of them
    assert by["app.things.fetch"].is_async
    assert by["app.things.fetch"].raises[0].condition is None
    route = by["GET /items/{item_id}"]
    assert route.kind == "route" and route.route_path == "/items/{item_id}"
    assert by["POST /legacy"].kind == "route"
    box = by["app.things.Box"]
    assert box.kind == "class" and [p.name for p in box.params] == ["n"]
    assert box.examples[0].setup == ["b = Box(3)"]
    assert "app.things.Box.size" in by
    assert not by["app.things.Box._hidden"].exported
    assert "app.things.Box.__repr__" not in by
    assert {a.module for a in result.apps} == {"app.things"}
    assert "fastapi" in result.imports


def test_python_syntax_error_is_reported() -> None:
    result = python.analyze("bad.py", "def oops(:\n")
    assert result.parse_error and not result.units


def test_jslex_masks_comments_strings_templates_and_regexes() -> None:
    src = (
        'const a = "{"; // }\n/* { */ const re = /[{}]/g; const t = `x ${ {a:1}.a } }`;\nf(a) / 2;'
    )
    masked = jslex.mask(src)
    assert len(masked) == len(src) and masked.count("\n") == src.count("\n")
    assert "{" not in masked.split("\n")[0]
    assert "f(a) / 2" in masked  # division is not a regex
    open_at = masked.index("(")
    assert masked[jslex.match_close(masked, open_at)] == ")"


def test_typescript_functions_classes_examples_throws_routes() -> None:
    src = """
import express from "express";
/**
 * Add two numbers.
 * @example
 * add(1, 2) // => 3
 */
export function add(a: number, b: number = 0): number {
  if (a < 0) {
    throw new RangeError("a must not be negative");
  }
  return a + b;
}

export const double = (n: number): number => n * 2;
const inc = x => x + 1;

export class Counter<T> {
  private items = new Map<string, number>();
  constructor(start: number) {
    if (start < 0) throw new Error("no");
  }
  /** Bump. */
  async bump(by: number): Promise<{ ok: boolean }> {
    return { ok: by > 0 };
  }
  static create(): Counter<number> {
    return new Counter(0);
  }
}

const app = express();
app.get("/health", (req, res) => res.send("ok"));
"""
    result = javascript.analyze("src/math.ts", src)
    by = {u.qualname: u for u in result.units}
    add = by["src/math.add"]
    assert add.language == "typescript" and add.exported and add.returns == "number"
    assert [(p.name, p.annotation, p.default) for p in add.params] == [
        ("a", "number", None),
        ("b", "number", "0"),
    ]
    assert add.examples[0].expression == "add(1, 2)" and add.examples[0].expected == "3"
    assert add.raises[0].exception == "RangeError" and add.raises[0].condition == "a < 0"
    assert by["src/math.double"].returns == "number"
    assert not by["src/math.inc"].exported
    counter = by["src/math.Counter"]
    assert [p.name for p in counter.params] == ["start"]
    assert counter.raises[0].condition == "start < 0"
    bump = by["src/math.Counter.bump"]
    assert bump.is_async and bump.returns == "Promise<{ ok: boolean }>"
    assert "src/math.Counter.create" in by
    assert "src/math.Counter.Map" not in by
    assert by["GET /health"].kind == "route"
    assert "express" in result.imports


def test_javascript_test_files() -> None:
    assert javascript.is_test_file("src/a.test.ts") and javascript.is_test_file("__tests__/x.js")
    assert not javascript.is_test_file("src/a.ts")


def test_demo_python_project() -> None:
    result, referenced = analyzer.analyze(_files("python-shop"))
    assert result.languages == ["python"]
    assert result.frameworks == ["fastapi"]
    assert result.test_frameworks == ["pytest"]
    assert result.test_files == ["tests/test_pricing.py"]
    assert "fastapi" in result.dependencies["python"]
    assert referenced == {"app.pricing.apply_discount"}
    summary = result.summary()
    assert summary["by_kind"]["route"] == 4
    assert summary["apps"][0]["module"] == "app.main"


def test_demo_typescript_project() -> None:
    result, referenced = analyzer.analyze(_files("ts-toolkit"))
    assert result.languages == ["typescript"]
    assert result.test_frameworks == ["vitest"]
    assert referenced == {"src/money.formatPrice"}
    kinds = {u.kind for u in result.units}
    assert kinds == {"function", "class", "method", "route"}


def test_dependency_files_and_frameworks() -> None:
    files = {
        "pyproject.toml": '[project]\ndependencies = ["Flask>=3", "pytest"]\n[dependency-groups]\ndev = ["ruff"]\n',
        "requirements-dev.txt": "# comment\n-r base.txt\nhttpx==0.28\n",
        "package.json": '{"dependencies": {"react": "19"}, "devDependencies": {"jest": "29"}}',
        "web/app.js": "export function f() { return 1; }\n",
        "broken/package.json": "{not json",
        "app.py": "x = 1\n",
    }
    result, _ = analyzer.analyze(files)
    assert result.dependencies["python"] == ["flask", "httpx", "pytest", "ruff"]
    assert result.dependencies["javascript"] == ["jest", "react"]
    assert result.frameworks == ["flask", "react"]
    assert result.test_frameworks == ["jest", "pytest"]
    assert analyzer.language_of("x.mts") == "typescript" and analyzer.language_of("x.md") is None
