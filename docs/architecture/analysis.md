# Source analysis

What TestForge learns about a project before writing a single test, and how it learns it
without running anything. The code is `apps/api/src/testforge/analysis/`: `python.py`,
`jslex.py`, `javascript.py`, `analyzer.py`, `model.py`.

## Never executes, never imports

Analysis reads source text only. Python is parsed with the standard library's `ast`;
JavaScript and TypeScript are read through a small masking lexer. No module of the
project is imported, no `setup.py`, `conftest.py`, `package.json` script or build step is
run, and nothing is installed. A project's code runs in exactly one place, the sandbox
([ADR-0004](adr/0004-static-analysis-never-executes-code.md)). The worker runs analysis in
a thread, so a large project never blocks the event loop, and records its time
(`testforge_analysis_seconds`, `source_imports.analysis_ms`).

## Input: the snapshot

An import becomes a snapshot first (`sources/archive.py`): a map of text files, never a
directory on disk.

- Absolute paths, `..`, backslashes, NUL and control characters, symbolic and hard links
  and device files are skipped.
- The entry count, each file's size (`MAX_FILE_BYTES`) and the total uncompressed size
  (`MAX_SNAPSHOT_BYTES`, `MAX_SNAPSHOT_FILES`) are capped while reading, never after: each
  member is read to at most one byte past its cap, so a lying header cannot inflate past it
  (a ZIP bomb stops at the cap).
- Dependency folders, virtualenvs, caches and build output (`.git`, `node_modules`,
  `.venv`, `venv`, `__pycache__`, `dist`, `build`, `.next`, `coverage` and others),
  compiled and binary files, lock files and anything that is not UTF-8 text are left out;
  a run never uses them.
- A single wrapping top folder (as in GitHub tarballs) is removed.

## What is extracted

| | Python (`ast`) | JavaScript and TypeScript (masked text) |
| --- | --- | --- |
| Functions | Module-level `def` and `async def` | Top-level `function f()`, `export function`, `export default function`, and `const`/`let`/`var` bound to an arrow function or a `function` expression |
| Classes and methods | Module-level classes and their methods; dunder methods are skipped, `__init__` gives the class its parameters, raises and statement lines | Top-level classes (`export`, `abstract`); methods at the class body's own depth, with modifiers; `constructor` gives the class its parameters and raises |
| Routes | Functions decorated with `@<x>.get/post/put/patch/delete/head/options("/path")` or `@<x>.route("/path", methods=[...])`, with the prefix of an `APIRouter(prefix=...)` or `Blueprint(url_prefix=...)` assigned at module level | Calls `<x>.get/post/put/patch/delete("/path", ...)` with a literal path starting with `/` |
| Application objects | `app = FastAPI(...)` or `app = Flask(...)` at module level: what API tests drive in process | |
| Parameters and types | Positional, keyword-only, `*args`, `**kwargs`, annotations and defaults; `self` and `cls` dropped | Parameter names and type annotations; return type |
| Documentation | The docstring | The JSDoc description |
| Documented examples | Doctests: lines with no output are setup for the next line that has one | JSDoc `@example` lines of the form `call(args) // => result`, with preceding lines as setup |
| Raises | Every `raise` inside an `if`, with that `if`'s condition and the message; other raises without a condition | `if (condition) throw new X(...)`, with the condition |
| Statement lines | Every statement line of the body, without the docstring or nested definitions | Every non-blank body line that is not only a bracket |
| Exported | Names not starting with `_` (and `__init__`) | `export`-ed declarations; methods of exported classes unless `private` or `#private` |
| Imports | Top-level module names (absolute imports) | Package names from `from`, `require(` and `import(` (scoped packages keep their scope) |

Each unit becomes a `code_units` row with its source (up to 8000 characters) and these
details, which is what generation's schema-aware prompts are built from
([generation.md](generation.md)). A file that does not parse is recorded under
`parse_errors` and the rest of the project is still analyzed. `.d.ts` files and
`*.config.*` files are skipped.

Python module names follow the sandbox's import path: `app/pricing.py` is `app.pricing`,
and `src/shop/cart.py` is `shop.cart`, because the sandbox puts both the workspace and
`src/` on `PYTHONPATH`.

### The masking lexer

`jslex.mask` returns a copy of the source with the same length and the same line breaks,
in which the contents of comments, string literals, template literals and regular
expression literals are replaced by spaces. A `/` starts a regular expression after an
operator, an opening bracket or a keyword such as `return` or `typeof`, and is division
otherwise. Brace matching, depth maps, keyword search and comma splitting then work on
code only, and every offset still points at the same place in the original text, so
names, signatures and source are read from the original. It builds no syntax tree and
evaluates nothing.

## Languages and frameworks

| Detected | From |
| --- | --- |
| Languages | File extensions: `.py`; `.js`, `.mjs`, `.cjs`, `.jsx`; `.ts`, `.mts`, `.cts`, `.tsx` |
| Frameworks | Imports and declared dependencies (`requirements*.txt`, `pyproject.toml` dependencies, optional dependencies and dependency groups, `package.json` dependencies, dev and peer dependencies): FastAPI, Flask, Django, Express, Fastify, Koa, React, Next.js, Vue |
| Test frameworks | pytest (imported, declared, or a `conftest.py` present), else unittest; Vitest, Jest, Mocha (named in a test file or declared) |
| Test files | Python: `test_*.py`, `*_test.py`, `conftest.py`, or anything under a `tests` or `test` folder. JavaScript and TypeScript: `*.test.*`, `*.spec.*`, or under `__tests__` |

Test files are not analyzed as units; they are read to find what they refer to.

## The untested-code detector

A unit is **untested** when all of these hold:

1. it is exported (part of the module's public surface);
2. it is not a class (its methods are units of their own);
3. no existing test file refers to it: its name does not appear as an identifier in any
   test file, or, for a route, its path does not appear in any test file
   (`referenced_by_tests`);
4. no measured coverage reaches it: `covered_percent` is unset or zero.

The first three are known right after analysis, so a freshly imported project already
lists its untested units (`summary.untested`). The fourth sharpens it after every run:
coverage from the coverage tool is projected onto each unit's own statement lines
([LLD.md](LLD.md#coverage-projection-onto-units)), so a unit that is covered only
indirectly (called by something a test calls) stops counting as untested. Generation
without explicit units targets exactly these units first.

## Pull request scoping

`pulls/diff.py` reads each changed file's unified diff on the head side: added lines are
changed lines; a pure deletion marks the head line where the removed text was, since the
code around it changed meaning. Consecutive lines merge into ranges. After the head commit
is imported and analyzed, a unit (not a class) is in scope when its line range overlaps a
changed range of its file; every unit of an added file is in scope; removed files
contribute nothing. Generation for a pull request then targets those units only.

## Limits of the approach

Static analysis is fast, safe and deterministic, and it is approximate:

- **No type inference or evaluation.** Return values come only from documented examples;
  what a function returns for an undocumented input is not known, which is why the prompt
  tells the model not to guess and why the check cannot tell whether an expected value is
  right.
- **Dynamic definitions are invisible.** Functions replaced by decorators, `setattr`,
  metaclasses, `module.exports.x = ...` or `exports.x = ...` assignments, objects of
  functions, and routes registered with a computed path are not units.
- **Route detection is syntactic.** A JavaScript call like `<x>.get("/path", ...)` is read
  as a route whatever `<x>` is; Python routes need a literal path in the decorator.
- **References are by name.** A test file that mentions `total` counts as referring to
  every unit named `total`; a unit tested only through a differently named alias counts as
  unreferenced until coverage says otherwise.
- **Raise conditions are plain ones.** Only `if <condition>: raise` (or `throw new`) gives
  a condition; errors raised deeper in helpers are not attributed to the caller.
- **The JavaScript lexer is a lexer.** Unusual syntax can mislead the masking; the effect
  is a missed or misplaced unit, never code execution.

Coverage is the correction: it is measured, not inferred, and it overrides what the names
suggest.
