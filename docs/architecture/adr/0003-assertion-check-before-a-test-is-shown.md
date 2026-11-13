# ADR-0003: Refuse a test with no real assertion before anyone sees it

- **Status:** Accepted
- **Date:** 2026-11-13

## Context

The cheapest way for a model to "write tests" is to write tests that cannot fail: a call
with no assertion, `assert True`, `expect(x).toBe(x)`, an assertion after a `return`, or an
assertion about a constant that never touches the code. They inflate test counts and
coverage while proving nothing, and a developer skimming a long file will not always
notice. Asking the model nicely does not prevent it.

## Decision

Every generated test file goes through `generation/checks.py` before it is stored, shown
or run. A file is refused, with a code and a reason, when any test in it:

- has no assertion, or only placeholders (truthy constants, self-comparisons, constant
  comparisons, `or` with a truthy constant, `expect(<literal>)`, `expect(x).toBe(x)`);
- has its assertions only where they cannot run (after an unconditional `return`, `raise`
  or `pytest.skip`, inside `if False:` or `if (false) {}`);
- never calls the code it is meant to test;

or when the file does not parse (Python) or has unbalanced brackets (JavaScript and
TypeScript), or contains no test. The check reads code only (Python `ast`, the masking
lexer for JavaScript and TypeScript); it never runs it. Refused tests are kept only as a
name, code and reason on the generation; accepted ones keep the assertions the check
found, next to their code.

The full rules are in [generation.md](../generation.md#the-assertion-check).

## Consequences

**Good**
- A placeholder test never reaches a developer, never runs and never counts toward
  coverage.
- Refusals are visible (counted on the generation, in the dashboard, in the audit log and
  in metrics), so a weak model shows up as a high refusal rate.
- Deterministic and fast: no model call and no sandbox run to decide.

**Bad / caveats**
- A test whose assertion is real but wrong passes the check; review (tests arrive as
  `proposed`) and the failure explanation cover that.
- The check is syntactic: an assertion hidden behind an unusual helper pattern may be
  refused; a module-level helper containing `assert`, `self.assert*` calls, `pytest.raises`
  and Vitest matchers are recognised.
- One bad test refuses its whole file, since a model's entry is one file.

## Alternatives considered

- **Run each test once and keep the ones that pass**: needs a sandbox run per candidate,
  and a test that passes is not a test that can fail.
- **Mutation testing as the gate**: the strongest signal, but many sandbox runs per test;
  a roadmap candidate, not a 0.1.0 gate.
- **Trust the prompt**: models comply most of the time, which is not a guarantee.
