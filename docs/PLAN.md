# Euron Open TestForge: plan for 0.1.0

Source brief: `euron-open-source/briefs/16-testforge.md` (received 2026-11-13). The brief's
80 features across 8 areas and 7-phase roadmap are the source of truth for what TestForge
should eventually do; 0.1.0 scopes Phases 1 to 3 plus the parts of Phase 4 and 6 that make
the product genuinely usable end to end (API test generation, GitHub integration), leaving
performance/security testing at scale, 7+ additional languages, and the advanced AI agents
(self-healing, exploratory, bug reproduction) to Roadmap. Where the brief and the program
rules differ, the rules win: MIT licence (brief: Apache 2.0), the standard repo layout with
domain packages under `apps/api` and Next.js (brief: `frontend/`, `backend/`, plain React),
the program's own Postgres-backed queue (brief: Celery/Redis), Terraform for ECS on AWS
(brief: Kubernetes, pushed to Roadmap).

## Purpose

TestForge is a self-hosted platform that writes and runs tests for a developer's own code.
A developer connects a GitHub repository or uploads a project, and TestForge analyzes its
source, generates real unit and API tests with assertions grounded in the actual code (not
stub tests that always pass), executes them in an isolated sandbox, and reports coverage
and failures in plain language. Every generated test is visible before it is trusted, and
every execution, generated or uploaded, runs with no network access and no credentials, so
nobody has to choose between getting help writing tests and handing a tool the keys to
their machine.

It removes the two problems that keep teams from having the test suite they know they
should: writing tests is slow and unrewarding compared to shipping features, so untested
code accumulates; and an AI tool that runs your code to "help" is a real risk if it can
reach your network, your secrets, or another project's files. The outcome it guarantees:
**every test execution, whether it runs a generated test or a developer's own uploaded
code, happens in a sandboxed environment with no network access, no credentials, and a
fixed CPU, memory and time budget, so a generated test or an uploaded project can never
reach anything outside its own run.**

The name is the contract. A *forge* for tests must (1) actually produce tests grounded in
the real code, not generic boilerplate, (2) run them somewhere safe, not on the platform's
own server, (3) explain a failure instead of leaving a developer to re-read a stack trace
alone, and (4) show real coverage, not an estimate.

## Comparable products and what users expect

| Product | License | Self-hostable | Notes |
| --- | --- | --- | --- |
| CoverAgent (Qodo, formerly CodiumAI) | AGPL-3.0 | Yes, but marked unmaintained since mid-2025 | LLM-driven coverage-iteration loop; runs in the host's own environment with no dedicated isolation layer |
| Keploy | Apache 2.0 core | Yes | Record-and-replay from live traffic, not source-based generation; bring-your-own-LLM and production-traffic capture are Enterprise-only, not in the open core, despite "safe, isolated sandboxes" marketing |
| Diffblue Cover | Proprietary (free tier) | No | Reinforcement-learning search over compiled JVM bytecode; JVM-only, no cross-language story |
| Testim, Mabl, TestRigor, Tusk | Proprietary SaaS | No | Closed, vendor-hosted; code and data leave the user's infrastructure |

Expected by users of this category (table stakes): connect a repo or upload code; detect
the language and framework automatically; generate unit tests with real assertions, not
stubs; run them and show pass/fail plus coverage; some API test generation from an OpenAPI
spec; a CLI alongside any dashboard; bring your own LLM key.

**Why ours is worth starring:**

1. **Sandboxed execution is a first-class, open-source guarantee, not marketing copy.**
   CoverAgent runs in the host project's own environment with no isolation; Keploy's
   isolation-relevant capabilities are Enterprise-only. TestForge reuses Euron Open
   CodeJudge's unprivileged nsjail sandbox design (fresh namespaces per run, no network, a
   tight syscall filter, rlimits for CPU, memory, output and processes) for every
   execution, generated test or uploaded project, in the MIT-licensed core.
2. **No open-core bait-and-switch.** Keploy gates custom LLM integration and air-gapped
   deployment behind Enterprise; Diffblue's free tier scope is ambiguous; CoverAgent is
   abandoned. TestForge is MIT, fully usable from `docker compose up`, nothing held back.
3. **Model-agnostic from day one.** OpenAI, Anthropic, Gemini, Ollama, and any
   OpenAI-compatible endpoint, with a deterministic mock provider for tests, so no vendor
   is load-bearing for the project and no API key is required to try it.

## Acceptance criteria (each one is an automated test)

| # | Criterion | Test |
| --- | --- | --- |
| A1 | `make up && make demo` installs and seeds the stack; a user imports a demo project through the API and through the web app and generates a passing test suite with a real coverage number | e2e + integration |
| A2 | A generated test contains a real assertion grounded in the analyzed source (not a placeholder `assert True` or an empty test body); a test with no meaningful assertion is rejected before it is shown to the user | unit + integration |
| A3 | Every test execution, whether of a generated test or an uploaded project's own test suite, runs in the sandbox with no network interface reachable from inside it | integration (an attempted network call from inside a run fails) |
| A4 | A sandboxed run cannot read the platform's own credentials, another project's files, or any file outside its own workspace | integration |
| A5 | A run that exceeds its CPU, memory, output, or wall-clock limit is stopped and reported with the specific limit it crossed, never left running or silently truncated | integration |
| A6 | Source analysis correctly identifies the language and framework of a real demo Python project and a real demo JavaScript/TypeScript project, and lists its functions, classes, and existing test coverage gaps | integration |
| A7 | Generated API tests from an imported OpenAPI specification cover every documented operation at least once (status code and, where specified, a response schema check) | integration |
| A8 | A failing test's report explains which assertion failed, with the actual and expected values, in the same run that produced it, without re-running the test a second time just to get the explanation | integration |
| A9 | A GitHub pull request import correctly identifies the changed files between the PR's head and base, and offers to generate tests only for the functions and endpoints those files touch | integration |
| A10 | Every test run, its generated or uploaded source, its pass/fail result, and who triggered it are recorded in an append-only audit log, visible per project | integration |
| A11 | Tenant isolation: a member of one organization gets 404 for another organization's projects, generated tests, and run history | integration |
| A12 | Every acceptance criterion above passes with no external AI provider configured, using the deterministic mock provider; each real provider adapter is tested against a mock and is off by default | integration |

## Scope for 0.1.0

**In** (brief areas A, B, C, G in part; Phases 1 to 3 plus the safety-critical sandbox and
the useful parts of Phase 4 and 6):

- **Control plane:** organizations, projects, users, project roles (admin, editor,
  viewer), email and password sign-in, API keys, audit log (append-only).
- **Project import:** a GitHub repository (public or with a token) or a ZIP upload; Python
  and JavaScript/TypeScript only for 0.1.0 (brief's Phase 1 languages; Java, Go, PHP, and
  the rest are Roadmap).
- **Source analysis:** a codebase analyzer (functions, classes, routes, dependencies) per
  supported language; an untested-code detector; a coverage analyzer reading real coverage
  output (`coverage.py`, Istanbul) rather than estimating it.
- **AI test generation:** a unit test generator with schema-aware prompts built from the
  real analyzed source; an edge-case and negative-test generator; an API test generator
  from an imported OpenAPI specification; test documentation (plain-language description
  of what each generated test checks). A generated test with no real assertion is rejected
  before it reaches the user (A2).
- **Sandboxed execution:** every test run, generated or uploaded, executes in an
  unprivileged, network-isolated sandbox reused from Euron Open CodeJudge's nsjail design
  (fresh namespaces, no credentials, rlimits for CPU, memory, output, and processes, a
  wall-clock backstop). `pytest` for Python, `vitest` for JavaScript/TypeScript as the
  0.1.0 execution engines (brief's own "use existing frameworks" principle); Playwright,
  k6, and security-specific runners are Roadmap.
- **Failure analysis:** a bug analyzer that explains a failing assertion (actual versus
  expected) from the same run's output, without a second execution.
- **GitHub integration:** importing a repository and a pull request's diff to scope test
  generation to changed files; a webhook endpoint a developer can point a GitHub Action at.
  The GitHub Action itself, and GitLab integration, are Roadmap.
- **Coverage and reports:** a coverage report per run and per project over time; a test
  history; CSV and HTML report export.
- **Model providers:** `openai`, `anthropic`, `gemini`, `ollama`, `openai_compatible`, and
  a deterministic `mock` provider for tests and the demo. Keys sealed.
- **API and SDK:** the brief's REST surface (projects, import, analyze, tests
  generate/execute, runs, coverage, bugs/analyze, reports, webhooks), OpenAPI exported and
  drift tested; a Python SDK `euron-testforge` with a matching CLI.
- **Dashboard:** project overview (tests, pass/fail, coverage), source explorer, generated
  tests with their assertions, run history and failure detail, coverage over time, GitHub
  import and PR scoping, reports, settings (members, API keys, model providers).
- **Mock service** (`mockai`): a scripted model speaking the OpenAI, Anthropic, and Gemini
  wire formats, so tests, e2e, and the demo need no real provider key.

**Roadmap (not 0.1.0, from the brief's Phases 2, 4, 5, 6, and 7):** Java, Go, PHP, C#,
Ruby, Rust, C/C++ language adapters; browser/UI test generation and visual regression
(Playwright-based); performance and load testing (k6, Locust); dedicated security testing
(SQL injection, XSS, CSRF, fuzzing); self-healing tests; an exploratory testing agent; a
bug-reproduction agent that converts a bug report into a reproducible test; a flaky-test
detector; risk-based test prioritization and automatic regression selection; GitLab
integration and a published GitHub Action; microVM-based sandbox runners as a stronger
isolation tier; Kubernetes manifests.

## Architecture

```
web (Next.js 15) ──► api (FastAPI)  ──► PostgreSQL 16 (projects, generated tests, runs,
                         │  ▲                           coverage, audit log)
 SDK / CLI ──────────────┘  │              Redis 7 (rate limits, analysis cache)
                     worker(s) ──► model providers (or mockai)
                         │      ──► GitHub (import, PR diffs, webhooks)
                         └────────► sandbox (nsjail, no network, no credentials)
                     scheduler (webhook retries, retention)
```

One Python package `testforge` with process roles: `testforge api`, `testforge worker`,
`testforge scheduler`, `testforge sandbox` (separate image with nsjail, reused from
CodeJudge's `judge/sandbox.py` and its per-language `languages.yaml` pattern, covering
Python and JavaScript/TypeScript for 0.1.0).

**Generating and running a test.** The worker loads the project's cached source analysis
(functions, classes, routes, existing coverage), builds a schema-aware prompt from the
real code, and calls the model. A generated test is parsed and rejected if it has no
assertion reachable from its entry point (A2) before it is shown to the user or executed.
An accepted test, and any test from an uploaded project's own suite, runs inside the
sandbox under a CPU, memory, output, and wall-clock limit; the sandbox has no network
interface and sees only its own run's files. A failure's actual and expected values are
captured from the same execution and explained without a second run.

**GitHub pull requests.** Importing a pull request diffs its head against its base to list
changed files; test generation can be scoped to only the functions and endpoints those
files touch, and a webhook can report results back.

## Data model (main tables)

organizations, users, memberships (org role), projects, project_members (project role),
api_keys, sessions, audit_logs, model_providers (sealed key), source_imports (GitHub repo
or ZIP, commit, language, analysis cache), code_units (functions, classes, routes
discovered per import), generated_tests (source, assertion check, status), test_runs
(sandbox result: exit code, timing, resource usage, pass/fail), coverage_reports
(per run and per project), pull_request_imports (base, head, changed files), webhooks,
usage_daily.

## API surface

The brief's endpoints, under `/api/v1`, scoped to a project by an API key or session, plus:
auth (login, logout, me), projects and members, imports (GitHub repo, ZIP, pull request),
analyze (source analysis status and results), tests (generate, list, get), runs (execute,
get, list, coverage), bugs (analyze a failure), reports (generate, download), webhooks
(configure, receive), usage (by project, model, day), system (health).

## Screens

Projects (list, import from GitHub or ZIP), project overview (tests, pass/fail, coverage
trend), source explorer (functions, classes, routes, coverage gaps), generated tests
(source, assertion, explanation, accept or regenerate), run detail (sandbox output,
resource usage, failure explanation), pull request imports (changed files, scoped
generation), reports, settings (members, API keys, model providers). Sign in, empty states
that teach, light and dark, phone width.

## Terraform

Modules copied from the published references: network, database (RDS PostgreSQL), cache
(ElastiCache), storage (S3, for uploaded ZIPs and reports), kms, secrets, email (SES), ecr,
service (ECS Fargate: api, worker, scheduler, web behind an ALB), sandbox (EC2 Auto Scaling
group with the unprivileged nsjail container, reused from CodeJudge's judge module),
observability (CloudWatch logs, alarms for queue backlog and sandbox failures). Envs
`local-floci`, `aws-dev`, `aws-prod`.

## Test plan

- **Unit:** source analysis per language (fixtures), assertion-reachability check (A2),
  prompt assembly, coverage parsing (`coverage.py`, Istanbul output), provider message
  translation per provider (fixtures), sealing, PR diff scoping.
- **Integration (real Postgres, Redis, mockai, and the real sandbox against real demo
  Python and JavaScript/TypeScript projects):** every endpoint, auth and roles, tenant
  isolation, A1 to A12, a network call from inside a sandboxed run refused, a run over its
  resource limit stopped and reported, GitHub import and PR diff scoping.
- **E2E (Playwright):** sign in; import a demo project; generate and review a test; run it
  and see the result and coverage; see a failure explained; import a pull request and
  generate scoped tests; viewer has no generate-or-execute controls.
- **Infrastructure:** validate, tflint, checkov, local-floci apply in `make up`,
  `make tf-aws-on-floci`.
- **QA:** Puppeteer sweep of every page, both themes, desktop and phone.
- **Bench:** source analysis time for a real-sized demo project, sandbox cold-start and
  per-run overhead, test generation latency excluding model time.

## Ports

web 5610, api 5630, sandbox 5635, postgres 5642, redis 5679, floci 5666, mailpit 5625,
mockai 5650, tf-aws-on-floci 5696.
