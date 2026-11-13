# Test generation

How TestForge turns analyzed source into tests a developer can trust, and why a test that
cannot fail never reaches them. The code is `apps/api/src/testforge/generation/`:
`prompt.py`, `checks.py`, `templates.py`, `service.py`.

## What can be generated

| Kind | For | Framework |
| --- | --- | --- |
| `unit` | A function, method or class: documented behaviour, documented examples | pytest (Python) or Vitest (JavaScript, TypeScript) |
| `edge` | Boundaries of the same units: the values on either side of a raise condition | same |
| `negative` | Inputs that must raise: the conditions the source raises under | same |
| `api` | Every operation of an imported OpenAPI 3 document, against the project's FastAPI or Flask application object, in process | pytest |

A generation is scoped by explicit unit ids, by a pull request import (the units its
changed lines touch, [analysis.md](analysis.md)), or by default to exported units no test
refers to and no coverage reaches, up to `MAX_UNITS_PER_GENERATION` (25).

## Schema-aware prompts

The prompt is built from the analysis, not from file text alone. Each unit becomes one
JSON object (`prompt.unit_payload`):

| Field | From |
| --- | --- |
| `id`, `kind`, `name`, `qualname`, `module`, `file`, `lines` | the code unit |
| `signature`, `params` (name, annotation, default, kind), `returns` | the parsed definition |
| `docstring` | the docstring or JSDoc description |
| `examples` | doctests or JSDoc `@example` lines: setup statements, the expression, the documented result |
| `raises` | each error the unit raises, with the exact condition when it is a plain `if <condition>: raise X(...)` (or `throw new X(...)`), and the message |
| `class_name`, `class_examples` | for methods: the class and how its own documentation builds it |
| `source` | the unit's source, cut to `max(400, PROMPT_SOURCE_CHARS / units)` characters |

The request (`mode`, `language`, `framework`, `kinds`, the units, the developer's extra
instructions) is placed between `<testforge-request>` tags in the user message. The system
message states the rules: every test must contain at least one real assertion about the
code under test, grounded in the source or its documentation; never assert a constant or a
value against itself; do not guess return values the source does not establish; tests run
with no network and only the standard library, the test framework and the toolchain's
libraries. It asks for one JSON object: `{"tests": [{"name", "target", "kind", "code",
"description"}]}`, one whole test file per entry, with a one or two sentence description
that becomes the test's documentation.

Framework rules are added per request: pytest imports the code by its module path (the
project root and `src/` are on the path) and uses `pytest.raises` and `pytest.approx`;
Vitest tests import from `"vitest"` and the code as `"../<path>"`, because the file is
written to `testforge/<name>.test.ts`; API tests use `TestClient(app)` or
`app.test_client()`, never a network connection, and set `target` to the operation key.

Every provider gets the same prompt at temperature 0. The deterministic `mock` provider
reads the same JSON and writes tests only from facts in it: documented examples become
equality assertions, simple raise conditions become boundary and negative tests,
documented operations become API tests. When a unit offers nothing to ground a test in, it
writes what a weak model writes, a call with no assertion, and the check refuses it, so the
guard is visible in the demo.

The answer is parsed leniently in form and strictly in content: bare JSON, a fenced block,
or the outermost braces are accepted; an entry without a `code` string is skipped; an
unknown `kind` becomes `unit`. An answer with no JSON or no `tests` list fails the
generation with `bad_answer`.

## The assertion check

Every test file the model returns goes through `checks.check(language, code, targets)`
before it is stored. It reads the code only; it never runs it
([ADR-0003](adr/0003-assertion-check-before-a-test-is-shown.md)). A file is refused when
**any** test in it fails a rule, with one of four codes:

| Code | Refused when |
| --- | --- |
| `syntax_error` | Python: the file does not parse. JavaScript and TypeScript: braces or parentheses are unbalanced in the masked text |
| `no_tests` | The file contains no test |
| `no_assertion` | A test has no meaningful assertion that can run |
| `not_grounded` | A test never calls the code it is meant to test |

`targets` are the names the test must call: the unit the entry names and its class; every
unit and class name of the request when the entry names none; for API tests the HTTP
client calls `get`, `post`, `put`, `patch`, `delete`, `head`, `options`, `request`.

### Python rules

Tests are top-level functions whose name starts with `test` (sync or async) and methods
starting with `test` of top-level classes starting with `Test`. Each test's body is walked
statement by statement:

- **An `assert` counts** unless its expression is a truthy constant (a non-zero or
  non-empty literal, a non-empty tuple, list, set or dict, `not` of a falsy constant) or a
  tautology: a single comparison of an expression with itself by `==`, `is`, `>=` or `<=`;
  a comparison of two constants; an `or` with a truthy constant operand.
- **A call counts as an assertion** when it is `<x>.assert...(...)` with at least one
  non-constant argument (`self.assertEqual(total, 30)`); when it is
  `pytest.raises(Error, fn, *args)` (the call form asserts, and calls `fn`); or when it
  calls a module-level helper (a function not starting with `test`) whose body contains an
  `assert`.
- **`with pytest.raises(...)` or `pytest.warns(...)` counts** when its body does something
  other than `pass`.
- **Reachability**: nothing after an unconditional `return`, `raise`, `pytest.skip`,
  `pytest.xfail`, `pytest.fail` or `pytest.exit` in the same block counts; the body of
  `if <constant false>:` and `while <constant false>:` is skipped (its `else` is not);
  `try` bodies, handlers and `finally` are walked; nested function and class definitions
  are not part of the test.
- **Grounded**: the test calls a target name anywhere in its walked statements (including
  inside assertions and context expressions). A module-level object built by calling a
  target (`client = TestClient(app)`) counts for any test that makes a method call on
  something, since that is how the fixture is used.

### JavaScript and TypeScript rules

The check runs on the lexer's masked text ([analysis.md](analysis.md)), so comments and
strings never look like code:

- Tests are calls to `it(` or `test(`, with `.only`, `.concurrent` or `.fails`; `.skip`
  and `.todo` are ignored. The test body is the callback at the call's own bracket level,
  an arrow function (block or expression body) or a `function`.
- **Reachable range**: up to the first `return` at the body's own depth, minus any
  `if (false) { ... }` or `if (0) { ... }` block.
- **An `expect(subject)` counts** when it is followed (through any `.not`, `.resolves`,
  `.rejects`) by one of these matchers: `toBe`, `toEqual`, `toStrictEqual`, `toThrow`,
  `toThrowError`, `toMatch`, `toMatchObject`, `toContain`, `toContainEqual`,
  `toHaveLength`, `toHaveProperty`, `toBeCloseTo`, `toBeGreaterThan`,
  `toBeGreaterThanOrEqual`, `toBeLessThan`, `toBeLessThanOrEqual`, `toBeTruthy`,
  `toBeFalsy`, `toBeNull`, `toBeUndefined`, `toBeDefined`, `toBeNaN`, `toBeInstanceOf`,
  `toBeTypeOf`, `toHaveBeenCalled`, `toHaveBeenCalledWith`, `toHaveBeenCalledTimes`,
  `toSatisfy`. It does not count when the subject is a literal (`true`, `false`, `null`,
  `undefined`, a number, a plain string) or when the subject's text equals the expected
  text (`expect(x).toBe(x)`).
- **An `assert(...)` or `assert.<name>(...)` counts** when its arguments are not a single
  literal.
- **Grounded**: a call to a target name inside the reachable range, as a plain call, a
  method call (`.name(`), a constructor (`new Name(`), with or without type arguments.

### What a refusal looks like

A refused file is never stored as a test, never shown as one and never run. The
generation keeps `{name, code, reason}` for it ("`test_total` has no meaningful assertion
that can run (a test that cannot fail proves nothing)"), counts it in `rejected_count`, and
the dashboard and audit log say how many were refused and why. Accepted tests keep the
assertions the check found (`[{test, line, text}]`), so a reviewer sees what each test
actually asserts next to its code. Metrics count each outcome
(`testforge_generated_tests_total{outcome="accepted"|"rejected_<code>"}`).

The check proves that a test asserts something about the code and can fail. It does not
prove the asserted value is right: a model can still assert a wrong expectation. That is
why tests arrive as `proposed`, a person accepts them, and a failing test's explanation
shows exactly what the code returned against what the test expected.

## API tests and the operation coverage guarantee

`POST /specs` imports an OpenAPI 3 document (JSON or YAML, up to `MAX_SPEC_BYTES`) into
its operations: key (`GET /items/{id}`), operation id, parameters (path-level and
operation-level, `$ref`s resolved), the JSON request body schema, and each response's
JSON schema.

An API generation needs an application object in the import (`app = FastAPI()` or
`app = Flask(...)` at module level, found by analysis); without one it is refused with
`no_app`. The prompt carries the app (`framework`, `module`, `attr`), every operation and
the document's components. The model's tests go through the same assertion check with the
HTTP call names as targets; an accepted test whose `target` is a documented operation key
marks that operation covered.

Then every documented operation the model skipped (or whose tests were refused) gets a
test built from the document itself (`templates.api_test`):

- path parameters filled with a sample value valid for their schema (the schema's
  `example`, `default`, first `examples` entry or first `enum` value, else the simplest
  value of its type), required query parameters likewise, and a sample JSON body built
  from the required properties of the request schema;
- `assert response.status_code in (<every documented status code>)`;
- for a documented 2xx response with a schema: when the status is that code, the body is a
  list (each item carrying the schema's required keys) or an object carrying its required
  keys.

These templates pass the same check before they are stored. The generation records
`operations_covered`, so every documented operation has at least one test with a status
code check and, where the document specifies one, a response shape check.

## Failures explained from the same run

`bugs/explain.py` turns a failed test case into a structured failure and one plain
paragraph, from what the plugin captured when the assertion failed:

| Captured | Explanation |
| --- | --- |
| A comparison (operator and both operands) | "`<test>` failed at `<file>:<line>`: the assertion (`<line of source>`) expected the value to equal `<expected>`, but the code returned `<actual>`." plus a concrete hint: for lists of different lengths, the counts; for lists that differ, the first differing index and, for numbers, the sums ("The items add up to 99.99 instead of 100.0"); for numbers, the difference; for dicts, missing, unexpected and changed keys |
| `DID NOT RAISE <class 'X'>`, or Vitest's "expected [Function] to throw" | It expected the call to raise `X`, but the call returned normally |
| Another assertion error | Its first line |
| Any other error | The test stopped with an error before it could check anything: the code or the test's setup raised, not an assertion |
| A test stopped by a limit | The limit and its sentence |

No test is ever run a second time to produce this. `POST /bugs/analyze` returns the same
structured failure for one case, and with `use_model: true` also asks the project's model
for a three-sentence narrative from those captured values only.
