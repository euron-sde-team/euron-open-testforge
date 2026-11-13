# testforge (API, worker, scheduler and sandbox service)

The Python package behind Euron Open TestForge: the FastAPI API, the worker, the
scheduler, the sandbox service, and the `testforge` command that starts every role. One
package, two images: `server.Dockerfile` (API, worker, scheduler, mock services) and
`sandbox.Dockerfile` (the sandbox service with nsjail and the test toolchains). The server
image never executes project code; only the sandbox does.

## Layout

```
src/testforge/
  core/          settings, database, Redis, sealing, storage, mail, middleware, errors
  sources/       imports: ZIP uploads and GitHub archives unpacked defensively (archive.py),
                 the GitHub client (github.py), snapshots, files and code units
  analysis/      static analysis, nothing executed: python.py (ast), javascript.py and
                 jslex.py (TypeScript and JavaScript), analyzer.py (languages, frameworks,
                 untested code)
  specs/         imported OpenAPI 3 documents and their operations
  pulls/         pull request imports; diff.py scopes generation to the changed units
  generation/    prompts from the analyzed source, answer parsing, the assertion check
                 (checks.py, every generated test must pass it) and test templates
  sandbox/       the sandbox service: jail.py (nsjail, CodeJudge's design), runners.yaml
                 (pytest and Vitest), server.py, client.py, classify.py (which limit was
                 crossed) and toolchain/ (the pytest plugin and Vitest reporter every run uses)
  runs/          runs through the sandbox, their test cases and results
  coverage/      coverage.py and Istanbul reports, per run and over time
  bugs/          failure explanations from the values the same run captured
  reports/       CSV and HTML exports
  webhooks/      outbound webhooks with retries, the inbound GitHub webhook
  jobs/          the Postgres job queue, its handlers and periodic tasks
  providers/     openai, anthropic, gemini, ollama, openai_compatible, and the
                 deterministic mock (mock/responder.py)
  auth/ users/ orgs/ projects/ instance/ audit/ usage/ overview/ system/
  migrations/    Alembic
  demo/          the demo projects (projects/) and make demo
  cli.py         the testforge command
src/mockai/      test fixture: model providers in four wire formats, a GitHub API serving
                 the demo repositories, a webhook receiver
tests/           unit/, integration/ (real Postgres, Redis, mock services, sandbox),
                 sandbox/ (inside the sandbox image), bench/
```

Architecture: [docs/architecture/](../../docs/architecture/). Start with
[HLD.md](../../docs/architecture/HLD.md) and [sandbox.md](../../docs/architecture/sandbox.md).

## Commands

```bash
uv sync                                 # dependencies (Python 3.12)

uv run testforge serve                  # the API on $PORT (8080)
uv run testforge worker                 # imports, generation, runs
uv run testforge scheduler              # lease reaper, webhook deliveries, retention
uv run testforge sandbox                # the sandbox service (needs nsjail: use the image)
uv run testforge migrate                # apply migrations
uv run testforge revision -m "..."      # autogenerate a migration from the models
uv run testforge create-admin --email you@example.com
uv run testforge seed-demo              # the demo (expects the Compose stack)
uv run testforge openapi                # print the OpenAPI document as YAML
```

Configuration is environment only: [docs/guides/configuration.md](../../docs/guides/configuration.md).

## Tests

```bash
uv run pytest tests/unit                       # no database, no network
uv run pytest tests/unit tests/integration     # needs Postgres, Redis, the sandbox
```

From the repository root, `make test`, `make test-integration`, `make test-sandbox`,
`make test-matrix` and `make bench` wrap these. Details:
[docs/guides/testing.md](../../docs/guides/testing.md).

## Licence

MIT, see [LICENSE](../../LICENSE).
