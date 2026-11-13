# ADR-0004: Static analysis never executes code

- **Status:** Accepted
- **Date:** 2026-11-13

## Context

Generation needs to know a project's functions, classes, routes, signatures, documented
examples and raise conditions. The most accurate way to learn them is to import the code
and introspect it (`inspect`, running the TypeScript compiler, executing `package.json`
scripts). Importing a Python module runs its top-level code; installing dependencies runs
install scripts. Doing that on the worker, which holds the database URL, provider keys and
GitHub tokens, would break the guarantee that untrusted code only runs in the sandbox.

## Decision

- Python is parsed with the standard library's `ast`; nothing is imported.
- JavaScript and TypeScript are read through a small masking lexer (`analysis/jslex.py`)
  that blanks comments, strings, template literals and regular expressions while keeping
  every offset, and regular expressions over the masked text find declarations, methods,
  routes, JSDoc and throw conditions. No compiler, no Node process.
- Nothing is installed and no build step runs. Analysis runs in a thread of the worker
  and reads only the in-memory snapshot.

## Consequences

**Good**
- The only place project code runs is the sandbox.
- Fast and deterministic; the same snapshot always gives the same units.
- No toolchain per language on the worker.

**Bad / caveats**
- No type inference and no evaluated values; dynamic definitions (decorator factories,
  `setattr`, `module.exports.x = ...`) are not units.
- The JavaScript reading is heuristic; unusual syntax can hide a unit. Measured coverage
  from real runs corrects the untested-code view ([analysis.md](../analysis.md)).

## Alternatives considered

- **Import in the sandbox to introspect**: safe, but a sandbox run per import before any
  test exists, and a project that fails to import would yield nothing.
- **tree-sitter grammars**: a real parse tree for JavaScript and TypeScript, at the cost of
  native dependencies on the worker; a candidate when more languages arrive.
- **The TypeScript compiler API**: exact, but a Node toolchain on the worker and slow on
  large projects.
