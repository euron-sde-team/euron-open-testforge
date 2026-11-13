# Contributing

Thanks for helping improve Euron Open TestForge. This guide covers the workflow, the bar a
change has to clear, and the conventions the codebase follows.

## Ground rules

- **Open an issue first** for anything larger than a bug fix or a docs tweak, so we can
  agree on the approach before you invest time.
- **One concern per pull request.** A refactor and a feature are two PRs.
- **Security issues go through private reporting**, never a public issue. That includes
  any way out of the sandbox. See [SECURITY.md](SECURITY.md).
- By contributing you agree your work is released under the [MIT License](LICENSE).

## Development setup

Requirements: Docker, Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 22 and
pnpm 9 (`corepack enable`).

```bash
make up          # Postgres, Redis, Mailpit, Floci (provisioned by Terraform), mock services,
                 # sandbox, api, worker, scheduler, web
make demo        # three projects imported, tests generated and run in the sandbox
make test        # unit tests (API and web)
```

The sandbox runs only inside its image (it needs nsjail and the toolchains): use
`make test-sandbox` for anything under `apps/api/src/testforge/sandbox/` or
`infra/docker/sandbox*`. [docs/guides/quickstart-local.md](docs/guides/quickstart-local.md)
walks through the local stack.

## Before you open a pull request

Each of these must pass:

```bash
make lint typecheck test
make test-integration                  # the API and worker against real Postgres, Redis and the sandbox
make test-sandbox                      # when you touched the sandbox, a runner or its image
make e2e                               # when you touched a web flow or infrastructure
make tf-validate tf-lint tf-security   # when you touched infra/terraform
make tf-aws-on-floci                   # same: apply and destroy aws-dev against Floci
make openapi                           # when you changed an endpoint
make sanitize                          # no credentials, account ids, resource ids or dashes
```

## Conventions

**Package by domain.** `apps/api/src/testforge/<domain>/` owns its `router.py` (HTTP
only), `schemas.py` (the public contract), `service.py` (rules) and `models.py`.
Dependencies point inward: router, service, data. A domain calls another domain's service,
never its tables. Periodic work registers with `core/tasks.py`; background work is a job
kind in `jobs/handlers.py`.

**Code runs only in the sandbox.** Nothing outside `sandbox/` may import, execute or
install a project's code: analysis parses, the assertion check reads, imports unpack in
memory. A change that runs project code on the worker or the API will not be merged.

**The sandbox holds nothing it does not need.** It gets `SANDBOX_SECRET` and nothing else;
a change that gives it database, storage, provider or GitHub settings, a route to another
service, a capability, `privileged: true`, or a mount of the service's own files into a
jail will not be merged. Changes to the seccomp profile, the kafel policy, the mounts or
the limits need a hostile test in `apps/api/tests/sandbox/` that proves the change.

**No test reaches a developer without a real assertion.** Generated tests go through
`generation/checks.py` before they are stored. Loosening a rule needs a unit test showing
the placeholder it would let through is still refused.

**Limits come from measurements.** The sandbox measures CPU time and memory with `wait4`
and decides the limit crossed in a fixed order (see
[docs/architecture/sandbox.md](docs/architecture/sandbox.md)). Do not add guesses.

**Coverage is measured, never estimated.** Coverage comes from coverage.py and Istanbul
reports produced in the run.

**Configuration is validated.** A new setting goes in `core/config.py`, is documented in
[docs/guides/configuration.md](docs/guides/configuration.md) in the same PR, and
security-relevant ones are enforced by `guard()` at boot.

**Database changes are new migrations.** Change the models, then autogenerate a revision
with `uv run testforge revision -m "what changed"` against a local database and review it.
Never edit an applied one. Indexes for every new filter the API exposes belong in the same
revision.

**Comments explain why.** The code says what it does. Comments are for the constraint, the
attack or the trade-off that made it this way.

**Style.** ruff and mypy `--strict` for Python; ESLint and TypeScript strict for the web.
No em dashes or en dashes anywhere (the sanitization check enforces it).

## Adding a test runner or language

Install the toolchain in `infra/docker/sandbox.Dockerfile` under `/opt/toolchain` (pinned,
read-only for every run), add an entry to `apps/api/src/testforge/sandbox/runners.yaml`
with a plugin or reporter that writes `report.json` and `events.jsonl` with captured
operands, add the analysis for the language under `analysis/` and the check rules under
`generation/checks.py`, and add real-project, isolation and limit tests to
`apps/api/tests/sandbox/`. `make test-sandbox` must pass.

## Adding a model provider

Add an adapter under `apps/api/src/testforge/providers/adapters/`, its wire format to the
mock services (`apps/api/src/mockai/app.py`) so it is tested against a real HTTP server,
and the kind to the `model_providers` check constraint in a new migration.

## Commit messages

Imperative mood with an optional scope: `sandbox: classify output at the limit before
time`, `generation: refuse assertions after an unconditional return`. Explain the why in
the body when it is not obvious.

## Architecture decisions

Significant decisions are recorded in [docs/architecture/adr/](docs/architecture/adr/).
If your change reverses or extends one, add a new ADR rather than editing the old one.
