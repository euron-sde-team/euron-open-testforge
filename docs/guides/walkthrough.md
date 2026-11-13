# Walkthrough

A tour of the seeded demo, flow by flow. Everything in it was produced for real by
`make demo`: the repositories were imported from the mock GitHub and analyzed by the
worker, the tests were written by the deterministic mock model and passed the assertion
check, and every run executed in the sandbox. Start the stack and seed it first
([quickstart-local.md](quickstart-local.md)), then sign in at http://localhost:5610 as
`maya.chen@example.com` with the password `make demo` printed.

Maya owns the Acme Retail organization, so she is an admin of its three projects: **Shop
API** (Python, FastAPI), **Web Toolkit** (TypeScript) and **Sandbox checks** (an uploaded
project whose tests try to leave the sandbox).

## 1. Shop API: from import to a real bug

**Overview.** The project's numbers at a glance: accepted tests and how many wait for
review, how many generated tests were refused for having no meaningful assertion, the
latest runs and the coverage trend. The trend starts with the project's own suite, which
only tests pricing, and climbs as generated tests are added.

**Source.** The repository `euron-demo/python-shop` as analyzed: Python with FastAPI and
pytest detected, its files, and per file the functions, methods, classes and routes with
their signatures, documented examples and raise conditions. Units no test refers to and no
coverage reaches are marked as untested; they are what a generation targets by default.
Nothing here was imported or executed to find them ([analysis.md](../architecture/analysis.md)).

**Tests.** Every generated test with its code, the assertions TestForge found in it and
its plain description. The first generation asked for unit, edge and negative tests; the
seed accepted all of them except the `split_bill` tests other than the one built from its
documented examples. The generation also records the tests that were refused before anyone
saw them, each with its reason: for a unit with no documented example or raise condition
to ground a test in, the demo's model writes what a weak model writes, a call with no
assertion, and the assertion check refuses it.

**Runs: the failing `split_bill` run.** The run of the accepted generated tests failed,
and it failed on a real bug. `app/pricing.py` documents:

```python
>>> split_bill(100.0, 3)
[33.34, 33.33, 33.33]
```

but the code truncates every share to `33.33`. The test built from that example asserts
the documented value. The run detail shows the failing case with its explanation, computed
from the operands pytest captured at the moment the assertion failed, in that same run:
the assertion expected `[33.34, 33.33, 33.33]`, the code returned `[33.33, 33.33, 33.33]`,
they first differ at index 0, and the items add up to 99.99 instead of 100.0. The test was
never run a second time to get this. The run also shows its exit code, CPU time, wall time
and peak memory as the sandbox measured them, the output tails, and every test case.

**API tests.** The seed imported the project's OpenAPI document (**API specs**) and
generated API tests from it: each documented operation got at least one test that drives
the FastAPI app in process with `TestClient`, checks the status code against the documented
ones and, for a documented success response, the shape of the body. The run of everything
(`all`: the project's suite plus every accepted test) is the latest point on the coverage
trend.

**Coverage.** The line and branch coverage that coverage.py measured in each run, per
file with the missing lines, and the trend over runs. After a run, each unit's covered
share is projected back onto **Source**, so units covered only indirectly stop counting as
untested.

## 2. Pull request #12: tests for what changed

**Pull requests.** Pull request #12 of `euron-demo/python-shop` changes `split_bill` and
adds `restock_plan`. TestForge read its changed files and their patches from GitHub,
imported and analyzed the head commit, and mapped the changed lines onto units: the pull
request detail lists the changed files with their changed line ranges and the units in
scope. The seed then generated unit and negative tests scoped to exactly those units;
nothing else in the repository was touched. A GitHub webhook pointed at
`/api/v1/hooks/github/<project>` does the same automatically when a pull request is opened
or updated.

## 3. Sandbox checks: what a run cannot do

This project was uploaded as a ZIP: the shop's code plus two test files written to escape.

- `tests/test_network.py` tries to reach a payment gateway on the internet and the
  platform's own Postgres by name, and checks which network interfaces are up.
- `tests/test_escape.py` tries to read `~/.aws/credentials` and `/etc/passwd`, and checks
  that no variable with `SECRET` or `TOKEN` in its name is in the environment.

**Runs.** The run of the project's own suite is marked failed, and its failures are the
escape attempts, each refused and explained: the connections fail because the run has no
network (no interface but loopback, no route, no DNS), and the files do not exist inside
the jail, which mounts only read-only system directories, the toolchain and its own
workspace. The environment holds nothing of the platform's, because the jail's environment
is built from scratch.

The second import adds `tests/test_hang.py`, a test that sleeps for an hour, and the
project's wall clock limit was lowered to 8 seconds in its settings. That run is stopped
at the limit: its status is `limit_exceeded`, its message says the run was still going
after the wall clock limit, the tests that finished before it keep their results, and the
sleeping test is listed as the one that was running when the limit hit (recovered from the
event log, since the run never reached its final report). The sandbox was fine afterwards;
the next run worked.

## 4. Web Toolkit: the same flow in TypeScript

The TypeScript project went through the same steps with Vitest and Istanbul: imported
from `euron-demo/ts-toolkit`, its own suite run, unit and negative tests generated from
JSDoc examples and throw conditions, accepted and run, and pull request #4 (which adds
`truncate`) scoped.

## 5. Around the project

- **Reports**: an HTML report of the failing run and a CSV of the project, generated by
  the seed and downloadable.
- **Audit log**: every import, generation (with what was refused), review and run, with
  who triggered it, on which import and commit, and the result. It is append-only.
- **Settings**: members (Arjun is an editor, Sofia a viewer), the model providers (the
  mock, which generations use, and a disabled Anthropic provider that shows how a real
  one is configured),
  a `GitHub Actions` API key with the `read` and `execute` scopes, the GitHub repository and
  its webhook secret, a `Team chat` webhook subscribed to `run.finished`, and the run limits.

Sign in as `sofia.lopez@example.com` to see the same Shop API as a viewer: everything is
readable, and nothing can be imported, generated, accepted or run.

## Reading the code in the same order

1. `sources/service.py` and `sources/archive.py`: an import, from upload or tarball to a
   snapshot.
2. `analysis/analyzer.py`, `python.py`, `jslex.py`, `javascript.py`: the units.
3. `generation/prompt.py`, `generation/checks.py`, `generation/service.py`: the prompt, the
   check, the stored tests; `providers/mock/responder.py` for the demo's model.
4. `runs/service.py`: a run's workspace, the sandbox call, recording the cases.
5. `sandbox/server.py`, `jail.py`, `classify.py`, with [sandbox.md](../architecture/sandbox.md)
   open.
6. `bugs/explain.py` and `coverage/`: the explanation and the projection onto units.
7. `jobs/queue.py` and `worker.py`: how all of it is scheduled.
