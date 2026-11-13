# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-11-13

First public release: imports and static analysis for Python and JavaScript/TypeScript,
test generation with an assertion check, sandboxed runs with real coverage, failure
explanations, pull request scoping, the API, the SDK and CLI, and the web app.

### Added

- Project imports from a ZIP upload or a GitHub repository (the tarball of one commit,
  never a clone; public, or private with a sealed token), unpacked in memory with absolute
  paths, `..`, links and devices skipped and file count, file size and total size capped
  while reading.
- Static analysis that never executes code: Python with `ast`, JavaScript and TypeScript
  with a masking lexer. Functions, methods, classes, FastAPI, Flask and Express-style
  routes, application objects, parameters and types, docstrings and JSDoc, documented
  examples (doctests, `@example`), raise conditions, statement lines; language, framework,
  test framework and dependency detection; an untested-code detector that combines test
  references with measured coverage.
- Test generation for unit, edge, negative and API tests from schema-aware prompts built
  from the analysis, through any model provider: OpenAI, Anthropic, Gemini, Ollama, any
  OpenAI-compatible endpoint, and a deterministic mock that needs no key.
- The assertion check: a generated test is refused before anyone sees it when it has no
  assertion, only placeholders, assertions that cannot run, or never calls the code under
  test, or when the file does not parse. Refusals are kept with their reason and counted.
- API test generation from OpenAPI 3 documents (JSON or YAML), driving the FastAPI or
  Flask app in process; every documented operation gets at least one test with a status
  code check and, where specified, a response shape check, built from the document when
  the model skipped it.
- Review: generated tests arrive as proposed with their assertions and a plain
  description; accept, discard, or regenerate.
- The sandbox service: every run, generated or uploaded, executes in a fresh nsjail jail
  (user, PID, network, mount, IPC and UTS namespaces, uid 65534, a syscall filter, no
  network, no `/proc`, read-only system directories and toolchain, its own workspace)
  inside a container with every capability dropped, called by the worker over signed HTTP,
  one run at a time per process. pytest and Vitest runners with coverage.py and Istanbul
  coverage.
- CPU, memory, process, output and wall clock limits per run, set per project under
  instance ceilings; a run that crosses one is stopped and reported with the limit it
  crossed, and the tests that finished before it keep their results.
- Failure explanations from the same run: the pytest plugin and the Vitest reporter
  capture the operator and both operands when an assertion fails, and each failure says
  which assertion failed, what the code returned and what the test expected, with a
  concrete difference.
- Coverage reports per run, per file with missing lines, projected onto code units, and a
  trend per project.
- Pull request imports: changed files and lines from GitHub, the head commit analyzed, and
  generation scoped to the functions, methods and routes the change touches; an inbound
  GitHub webhook that does the same when a pull request is opened or updated.
- Outbound webhooks for `run.finished`, signed, delivered by the scheduler with retries
  and backoff.
- Reports in CSV and HTML, daily usage per project and model, and an append-only audit
  log of every import, generation, review and run with who triggered it.
- Organizations, projects, project roles (viewer, editor, admin), email and password
  sign-in with lockout, project API keys with scopes (`read`, `generate`, `execute`,
  `manage`), sealed secrets (AES-GCM locally, KMS on AWS), production boot guards.
- A PostgreSQL job queue with leases, renewals, a reaper and compare-and-set finishes;
  `?wait=` on import, pull request, generation and run endpoints.
- The web app: projects, overview, source explorer, tests, runs with failure detail,
  coverage, pull requests, API specs, reports, audit log, settings, instance
  administration; light and dark themes, phone width.
- The Python SDK `euron-testforge` (sync and async) and the `testforge-cli` command for CI.
- Mock services: model providers in four wire formats, a GitHub API serving the demo
  repositories and pull requests, and a webhook receiver.
- Docker Compose stack on Floci (`make up`), against real AWS (`make up-aws`), and
  Terraform modules and environments for AWS: ECS Fargate behind an ALB, the sandbox on an
  EC2 capacity provider, RDS, ElastiCache, S3, KMS, Secrets Manager, SES and CloudWatch
  alarms on the job queue and sandbox failures.
- Unit, integration, sandbox, end-to-end and browser QA suites, the backend matrix, and
  benchmarks.
