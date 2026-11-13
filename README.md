<p align="center">
  <img src="docs/assets/banner.svg" alt="Euron Open TestForge: tests with real assertions, run in a sandbox with no network" width="100%">
</p>

<p align="center">
  <img alt="Open source" src="https://img.shields.io/badge/open_source-%E2%9D%A4-10b981?style=flat">
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-3b82f6?style=flat"></a>
  <img alt="Python 3.12" src="https://img.shields.io/badge/python-3.12-3776ab?style=flat&logo=python&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-async-009688?style=flat&logo=fastapi&logoColor=white">
  <img alt="Next.js 15" src="https://img.shields.io/badge/Next.js-15-000000?style=flat&logo=nextdotjs&logoColor=white">
  <img alt="PostgreSQL 16" src="https://img.shields.io/badge/PostgreSQL-16-4169e1?style=flat&logo=postgresql&logoColor=white">
  <img alt="Terraform" src="https://img.shields.io/badge/IaC-Terraform-7b42bc?style=flat&logo=terraform&logoColor=white">
  <img alt="AWS" src="https://img.shields.io/badge/AWS-ready-ff9900?style=flat&logo=amazonwebservices&logoColor=white">
</p>

<p align="center">
  <a href="https://github.com/euron-sde-team/euron-open-testforge/stargazers"><img alt="Star this repo" src="https://img.shields.io/github/stars/euron-sde-team/euron-open-testforge?style=social&label=Star%20this%20repo"></a>
  <a href="https://github.com/euron-sde-team/euron-open-testforge/fork"><img alt="Fork" src="https://img.shields.io/github/forks/euron-sde-team/euron-open-testforge?style=social&label=Fork"></a>
  <a href="https://github.com/euron-sde-team/euron-open-testforge/watchers"><img alt="Watch" src="https://img.shields.io/github/watchers/euron-sde-team/euron-open-testforge?style=social&label=Watch"></a>
  <br>
  <a href="https://github.com/euron-sde-team/euron-open-testforge/issues"><img alt="Open issues" src="https://img.shields.io/github/issues/euron-sde-team/euron-open-testforge?style=flat&color=10b981"></a>
  <a href="https://github.com/euron-sde-team/euron-open-testforge/pulls"><img alt="PRs welcome" src="https://img.shields.io/badge/PRs-welcome-34d399?style=flat"></a>
  <a href="https://github.com/euron-sde-team/euron-open-testforge/commits/main"><img alt="Last commit" src="https://img.shields.io/github/last-commit/euron-sde-team/euron-open-testforge?style=flat&color=8b95a8"></a>
  <img alt="Runs locally with no AWS account and no model key" src="https://img.shields.io/badge/runs_locally-no_AWS_account_or_model_key-0a1110?style=flat">
  <br>
  <a href="#built-by-the-team-behind-euron"><img alt="Built by the team behind Euron" src="https://img.shields.io/badge/built_by-Euron-4f46e5?style=flat"></a>
</p>

<p align="center">
  <b><a href="#-quickstart">Quickstart</a></b> ·
  <b><a href="#️-architecture">Architecture</a></b> ·
  <b><a href="#-explore-the-repository">Explore the repo</a></b> ·
  <b><a href="docs/api/openapi.yaml">API reference</a></b> ·
  <b><a href="#️-deploy-to-aws">Deploy</a></b> ·
  <b><a href="docs/architecture/sandbox.md">Sandbox</a></b> ·
  <b><a href="#-documentation">Docs</a></b>
</p>

**Euron Open TestForge** is an open-source, MIT-licensed platform that writes and runs tests
for your own code, part of the open-source initiative of **ENGAGESPHERE TECHNOLOGY PRIVATE
LIMITED**. Connect a GitHub repository or upload a ZIP of a Python, JavaScript or TypeScript
project; TestForge analyzes the source without running it, writes unit, edge-case, negative
and API tests whose expected values come from the code and its documentation, refuses any
generated test that has no real assertion, runs tests in an unprivileged sandbox with no
network and no credentials, and reports real coverage and every failure in plain words.

It is built for the moment a team asks "can a tool write our tests, and can we let it run
code?", so the safety is structural:

- **Every run is sandboxed.** Generated tests and a project's own suite run in nsjail inside a
  container with no privileges: fresh namespaces, no network interface but a loopback, a
  syscall filter, and a CPU, memory, output and wall clock budget. The sandbox holds no
  credential but its request-signing secret and sits on a network that reaches nothing else.
- **No placeholder tests.** A generated test with no assertion, an `assert True`, an assertion
  that can never run, or one that never calls the code under test is refused before anyone
  sees it, and the refusal is shown with its reason.
- **Failures explained from the same run.** The actual and expected values are captured the
  moment an assertion fails, so the explanation never needs a second execution.

The whole stack runs on a laptop with no AWS account and no model key (a deterministic mock
model writes the tests until you add OpenAI, Anthropic, Gemini, Ollama or any compatible
endpoint), and deploys to AWS from the same Terraform.

<p align="center">
  <img src="docs/assets/tour.gif" alt="Product tour: projects, the overview, the source explorer with coverage, generated tests with their assertions and the refused ones, a run with a failure explained, the sandbox refusing network and file access and stopping a run at its limit, a pull request scoped, settings" width="100%">
</p>

> [!NOTE]
> Everything in the tour ran for real: Docker Compose on a laptop, the demo repositories
> imported from the bundled mock GitHub, tests written by the deterministic model and checked,
> every run executed in the nsjail sandbox, with S3, KMS and Secrets Manager emulated locally
> and provisioned by the same Terraform modules that build production. `make up && make demo`
> reproduces it.

<h3 align="center">Built by the team behind Euron</h3>

<p align="center">Euron Open TestForge comes from the people who build these platforms. If you like how this repository is built, come and see what we build with it.</p>

<p align="center">
  <a href="https://euron.one"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/assets/brand/euron-dark.svg"><img src="docs/assets/brand/euron-light.svg" alt="Euron: learn the latest technologies from industry experts. Visit euron.one" width="31%"></picture></a>
  <a href="https://euronsystems.com"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/assets/brand/euron-systems-dark.svg"><img src="docs/assets/brand/euron-systems-light.svg" alt="Euron Systems: the SaaS platform for educators and creators. Visit euronsystems.com" width="31%"></picture></a>
  <a href="https://alphaeuron.com"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/assets/brand/alpha-euron-dark.svg"><img src="docs/assets/brand/alpha-euron-light.svg" alt="Alpha Euron: where school kids grow creativity and tech skills with AI. Visit alphaeuron.com" width="31%"></picture></a>
</p>

<p align="center">
  <a href="https://www.instagram.com/euron_official"><img src="https://img.shields.io/badge/Instagram-E4405F?style=flat-square&logo=instagram&logoColor=white" alt="Instagram"></a>
  <a href="https://www.linkedin.com/company/euronone/posts/"><img src="https://img.shields.io/badge/LinkedIn-0A66C2?style=flat-square&logo=linkedin&logoColor=white" alt="LinkedIn"></a>
  <a href="https://x.com/euron712"><img src="https://img.shields.io/badge/X-000000?style=flat-square&logo=x&logoColor=white" alt="X"></a>
  <a href="https://www.youtube.com/@Euron-official"><img src="https://img.shields.io/badge/YouTube-FF0000?style=flat-square&logo=youtube&logoColor=white" alt="YouTube"></a>
  <a href="https://whatsapp.com/channel/0029VaeeJwq9RZAfPW9P2l07"><img src="https://img.shields.io/badge/WhatsApp_channel-25D366?style=flat-square&logo=whatsapp&logoColor=white" alt="WhatsApp channel"></a>
</p>

---

## 📚 Table of contents

- [Why Euron Open TestForge](#-why-euron-open-testforge)
- [At a glance](#-at-a-glance)
- [Screenshots](#️-screenshots)
- [Features](#-features)
- [Architecture](#️-architecture)
- [Tech stack](#-tech-stack)
- [Prerequisites](#-prerequisites)
- [Quickstart](#-quickstart)
- [Explore the repository](#-explore-the-repository)
- [API](#-api)
- [Configuration](#️-configuration)
- [Deploy to AWS](#️-deploy-to-aws)
- [Security model](#-security-model)
- [Testing](#-testing)
- [Documentation](#-documentation)
- [Roadmap](#️-roadmap)
- [FAQ](#-faq)
- [Contributing, security and license](#-contributing-security-and-license)

## 💡 Why Euron Open TestForge

Teams know which code has no tests; writing them loses to shipping features every week.
AI test generators promise to close the gap, but most write tests that assert nothing, and
the ones that run your code to check their work run it on your machine, next to your
credentials. Euron Open TestForge does both jobs and keeps them honest:

- **Tests grounded in the code.** Prompts carry each function's real signature, types,
  docstring, documented examples and the exact conditions under which it raises; expected
  values come from there, not from a guess.
- **A gate before trust.** Every generated test passes an assertion check before it is
  stored. Tests that cannot fail are refused, with the reason, so the suite you accept is a
  suite that tests something.
- **A sandbox as the guarantee, in the open core.** CodeJudge's unprivileged nsjail design,
  reused for every run, generated or uploaded: no network, no credentials, nothing outside
  the run's workspace, every limit enforced and named.
- **Real numbers.** Coverage comes from coverage.py and Istanbul, never an estimate, and a
  failure shows the actual and expected values from the run that failed.
- **Any model, your servers.** OpenAI, Anthropic, Gemini, Ollama or any OpenAI-compatible
  endpoint per project, keys sealed by KMS; a deterministic mock runs everything, including
  this repository's tests and demo, without a key.

## 📊 At a glance

| | |
| --- | --- |
| **Apps** | Web dashboard, API, worker, scheduler, sandbox service, Python SDK and CLI |
| **Languages** | Python (pytest, coverage.py), JavaScript and TypeScript (Vitest, Istanbul) |
| **Imports** | GitHub repositories at a branch, tag or commit; pull requests; ZIP uploads; OpenAPI 3 documents |
| **Model providers** | OpenAI, Anthropic, Gemini, Ollama, any OpenAI-compatible endpoint, built-in mock |
| **Safety** | nsjail per run (no network, uid 65534, read-only system, syscall filter), CPU, memory, output and wall clock limits, an assertion check on every generated test, append-only audit |
| **Tenancy** | Organizations, projects, roles (admin, editor, viewer), scoped API keys |
| **Infrastructure** | 11 Terraform modules, 3 environments (local emulator, AWS dev, AWS prod) |
| **Tests** | 177 API unit, 85 web unit, 56 integration on the real sandbox (89% coverage, run under 4 backend combinations), 15 sandbox suite in the hardened image, 11 browser end-to-end |
| **License** | MIT |

## 🖼️ Screenshots

| | |
| --- | --- |
| <img src="docs/assets/screenshots/01-projects.png" alt="Projects: tests, last run and coverage per project" width="100%"><br><sub>Projects: tests, last run and coverage per project</sub> | <img src="docs/assets/screenshots/02-overview.png" alt="A project at a glance: the next step, tests, refusals, pass rate, coverage over time" width="100%"><br><sub>A project at a glance: the next step, tests, refusals, pass rate, coverage over time</sub> |
| <img src="docs/assets/screenshots/03-source-explorer.png" alt="The source explorer: functions, classes and routes, with coverage" width="100%"><br><sub>The source explorer: functions, classes and routes, with coverage</sub> | <img src="docs/assets/screenshots/04-untested-units.png" alt="Untested code, and tests generated for exactly those units" width="100%"><br><sub>Untested code, and tests generated for exactly those units</sub> |
| <img src="docs/assets/screenshots/05-generated-tests.png" alt="Generated tests, each with what it asserts and what it checks" width="100%"><br><sub>Generated tests, each with what it asserts and what it checks</sub> | <img src="docs/assets/screenshots/06-refused-tests.png" alt="Tests refused before anyone saw them, with the reason" width="100%"><br><sub>Tests refused before anyone saw them, with the reason</sub> |
| <img src="docs/assets/screenshots/07-test-detail.png" alt="One test: its code, its assertions and the unit it tests" width="100%"><br><sub>One test: its code, its assertions and the unit it tests</sub> | <img src="docs/assets/screenshots/08-run-failure-explained.png" alt="A real bug: actual and expected from the same run, explained" width="100%"><br><sub>A real bug: actual and expected from the same run, explained</sub> |
| <img src="docs/assets/screenshots/09-sandbox-refusals.png" alt="An uploaded suite's attempts to leave the sandbox, all refused" width="100%"><br><sub>An uploaded suite's attempts to leave the sandbox, all refused</sub> | <img src="docs/assets/screenshots/10-limit-crossed.png" alt="A run stopped at its wall clock limit, the limit named" width="100%"><br><sub>A run stopped at its wall clock limit, the limit named</sub> |
| <img src="docs/assets/screenshots/11-coverage.png" alt="Coverage per file, from coverage.py and Istanbul" width="100%"><br><sub>Coverage per file, from coverage.py and Istanbul</sub> | <img src="docs/assets/screenshots/12-pull-request.png" alt="A pull request: changed lines and the units they touch" width="100%"><br><sub>A pull request: changed lines and the units they touch</sub> |
| <img src="docs/assets/screenshots/13-api-spec.png" alt="An OpenAPI document with every operation covered" width="100%"><br><sub>An OpenAPI document with every operation covered</sub> | <img src="docs/assets/screenshots/14-audit-log.png" alt="The audit log: what ran, from which commit, for whom" width="100%"><br><sub>The audit log: what ran, from which commit, for whom</sub> |
| <img src="docs/assets/screenshots/15-settings.png" alt="Settings: members, keys, providers, GitHub, webhooks, limits" width="100%"><br><sub>Settings: members, keys, providers, GitHub, webhooks, limits</sub> | <img src="docs/assets/screenshots/16-dark-run-failure.png" alt="Dark mode" width="100%"><br><sub>Dark mode</sub> |
| <img src="docs/assets/screenshots/17-dark-overview.png" alt="Dark mode overview" width="100%"><br><sub>Dark mode overview</sub> | <img src="docs/assets/screenshots/18-phone-run-failure.png" alt="Phone width" width="100%"><br><sub>Phone width</sub> |

## ✨ Features

| Area | What you get |
| --- | --- |
| **Import** | A GitHub repository as the archive of one commit (never cloned, no hook runs), a pull request's head with its changed files, or a ZIP; unpacked defensively (no links, no paths outside the project, file count and size caps) |
| **Analysis** | Functions, methods, classes and routes (FastAPI, Flask, Express style) from Python's `ast` and a TypeScript and JavaScript lexer, with parameters, types, docstrings, documented examples and raise conditions; languages, frameworks and test frameworks detected; code no test refers to flagged; nothing executed |
| **Generation** | Unit, edge-case and negative tests from the analyzed source; API tests from an imported OpenAPI document covering every operation; a plain-language description of each test; regenerate one test at a time |
| **The assertion check** | Every generated test must have a real, reachable assertion and must call the code it tests, or it is refused before it is stored; refusals are listed with their reason |
| **Runs** | Generated tests, the project's own suite, or both, in the sandbox with pytest or Vitest; CPU time, peak memory and output measured; a run that crosses a limit is stopped and reported with the limit it crossed |
| **Failures** | The failing assertion, the actual and expected values captured in the same run, the line, and an explanation; optionally a narrative from the project's model, from the same captured values |
| **Coverage** | Line and branch coverage per run from coverage.py or Istanbul, per file and per function, and over time |
| **Pull requests** | The files and lines a pull request changes, the functions and routes they touch, and generation scoped to exactly those; a GitHub webhook that imports pull requests as they open |
| **Reports and webhooks** | HTML and CSV reports of a run or of the project's history; signed outbound webhooks on `run.finished` with retries |
| **Access** | Organizations and projects, roles, API keys with `read`, `generate`, `execute` and `manage` scopes |
| **Audit and usage** | Append-only audit log per project (what ran, from which commit, the result, who triggered it), daily usage rollups, Prometheus metrics, JSON logs |
| **SDK and CLI** | `euron-testforge` for Python (sync and async) and `testforge-cli`, whose `run` exits non-zero unless every test passed |

## 🏗️ Architecture

<p align="center">
  <img src="docs/assets/diagrams/architecture.svg" alt="Architecture: the web app and API behind one load balancer; the worker imports and analyzes code, calls the model provider and sends runs to the sandbox, which sits on its own network; Postgres, Redis, S3 and KMS" width="100%">
</p>

One Python package, two images, five roles picked by the command:

- **api** (`testforge serve`): the REST API under `/api/v1`, sessions and API keys.
- **worker** (`testforge worker`): claims jobs from a Postgres queue (`FOR UPDATE SKIP
  LOCKED` with leases): imports and static analysis, generation and the assertion check, and
  runs, which it sends to the sandbox over signed HTTP.
- **scheduler** (`testforge scheduler`): reaps expired leases, delivers webhooks with
  retries, applies retention, publishes queue gauges.
- **sandbox** (`testforge sandbox`, its own image): runs one suite at a time in nsjail with
  pytest or Vitest and the run's budget, and returns measurements, results and coverage.
- **mockai** (local only): the deterministic model in four wire formats, a GitHub API serving
  the demo repositories, a webhook receiver.

### From an import to an explained failure

<p align="center">
  <img src="docs/assets/diagrams/run-flow.svg" alt="Import, analyze, generate, the assertion check, accept, run in the sandbox, results, coverage and failure explanations" width="100%">
</p>

1. An import is fetched (GitHub's archive of one commit, or the uploaded ZIP), unpacked
   defensively into a snapshot in object storage, and analyzed statically.
2. A generation builds a prompt from the units' real source and asks the project's model for
   tests; each one goes through the assertion check, and only those that pass are stored.
3. A developer reviews and accepts tests. A run sends the snapshot and the chosen tests to
   the sandbox, which runs them with no network under the run's limits.
4. The runner plugins record every outcome and, for a failed comparison, both values; the
   worker stores the cases, explains failures, projects coverage onto functions, writes the
   audit entry and queues the webhooks.

<p align="center">
  <img src="docs/assets/diagrams/sandbox-layers.svg" alt="Sandbox layers: the host, the unprivileged sandbox container, and nsjail per run with fresh namespaces and limits" width="100%">
</p>

[High-level design](docs/architecture/HLD.md) · [Low-level design](docs/architecture/LLD.md) ·
[Sandbox](docs/architecture/sandbox.md) · [Generation and the assertion check](docs/architecture/generation.md) ·
[Analysis](docs/architecture/analysis.md)

## 🧰 Tech stack

| Layer | Choice | Why |
| --- | --- | --- |
| API, worker, scheduler | Python 3.12, FastAPI, SQLAlchemy 2 (async), Alembic | Typed end to end (`mypy --strict`) |
| Sandbox | nsjail 3.6 in an unprivileged container, rlimits, a seccomp profile | Isolation without a privileged container ([ADR 0001](docs/architecture/adr/0001-unprivileged-nsjail-sandbox-service.md), [ADR 0002](docs/architecture/adr/0002-rlimits-not-cgroups.md)) |
| Runners | pytest with pytest-cov, Vitest with Istanbul, plus TestForge's own plugin and reporter | Real frameworks and real coverage; values captured at the failing assertion |
| Analysis | Python `ast`, a masking lexer for TypeScript and JavaScript | Static only, never executes the code ([ADR 0004](docs/architecture/adr/0004-static-analysis-never-executes-code.md)) |
| Queue | Postgres, `SKIP LOCKED`, leases | No broker to run ([ADR 0005](docs/architecture/adr/0005-postgres-job-queue.md)) |
| Web | Next.js 15, React 19, Tailwind 4, TanStack Query | Types generated from the OpenAPI document |
| Cache | Redis 7 (optional) | Rate limits, the file index cache, pub/sub wake-ups; never the only copy |
| AWS | ECS Fargate, EC2 for the sandbox, ALB, WAF, RDS, ElastiCache, S3, KMS, Secrets Manager, SES, CloudWatch | Managed building blocks, least-privilege roles |
| Infrastructure as code | Terraform | The same modules build AWS and the local emulator |
| Local AWS | Floci, Mailpit, `mockai` | Full stack on a laptop |
| Tests | pytest, Vitest, Playwright, Puppeteer | Unit, integration against the real sandbox, browser end-to-end, a QA sweep |

## 📋 Prerequisites

| Tool | Version | Used for |
| --- | --- | --- |
| [Docker](https://docs.docker.com/get-docker/) with Compose v2 | 24+ | The local stack (the sandbox needs a Linux kernel with user namespaces, which Docker Desktop provides) |
| [uv](https://docs.astral.sh/uv/) | 0.5+ | Running the API's tests outside Docker |
| [Node.js](https://nodejs.org/) and [pnpm](https://pnpm.io/) | 20+, 9 | The web app's tests, e2e and the QA sweep |
| [Terraform](https://developer.hashicorp.com/terraform/install) | 1.16 | Only for deploying to AWS (local runs use a pinned container) |

Free local ports (each overridable in `deploy/compose/.env`): 5610 (web), 5630 (API), 5642
(Postgres), 5679 (Redis), 5666 (AWS emulator), 5625 (Mailpit), 5650 (mock services), 5635
(the integration suite's sandbox), 5696 (`make tf-aws-on-floci`).

## 🚀 Quickstart

```bash
git clone https://github.com/euron-sde-team/euron-open-testforge.git
cd euron-open-testforge
make up      # builds the images, applies Terraform to the emulator, starts everything
make demo    # people, three projects imported, tests generated and run in the sandbox
```

| Open | As |
| --- | --- |
| http://localhost:5610 | `maya.chen@example.com` (admin), `arjun.mehta@example.com` (editor) or `sofia.lopez@example.com` (viewer); the password is printed by `make demo` |
| http://localhost:5630/docs | The interactive API reference |
| http://localhost:5625 | Every email the stack sends |

The first `make up` builds nsjail and the test toolchains into the sandbox image, which takes
a while on a slow link; set `TESTFORGE_APT_MIRROR` in `deploy/compose/.env` to a closer Debian
mirror if it crawls. [Quickstart guide](docs/guides/quickstart-local.md) ·
[Walkthrough](docs/guides/walkthrough.md)

## 🧭 Explore the repository

```
apps/api/src/testforge/   the API, worker, scheduler and sandbox (one package)
  sandbox/                jail.py (nsjail), server.py, classify.py, runners.yaml, toolchain/
  generation/             prompt.py, checks.py (the assertion check), templates.py
  analysis/               python.py, javascript.py, jslex.py, analyzer.py
  sources/ pulls/ specs/  imports, pull requests, OpenAPI documents
  runs/ coverage/ bugs/   runs, coverage, failure explanations
apps/api/src/mockai/      the mock model, mock GitHub and webhook receiver
apps/api/tests/           unit/, integration/, sandbox/ (hostile probes), bench/
apps/web/                 the Next.js dashboard
sdk/python/               euron-testforge and testforge-cli
infra/terraform/          modules and envs (local-floci, aws-dev, aws-prod)
infra/docker/             server, sandbox and web images, the sandbox seccomp profile
e2e/  scripts/qa/         Playwright journeys, the Puppeteer sweep and screenshots
```

| To understand | Read |
| --- | --- |
| Why a run cannot reach anything | `sandbox/jail.py`, `sandbox/server.py`, then `tests/sandbox/test_sandbox.py` and its probes in `tests/sandbox/hostile/` |
| How a limit is named | `sandbox/classify.py` and `sandbox/runners.yaml` |
| Why a placeholder test never reaches you | `generation/checks.py`, then `tests/unit/generation/test_checks.py` |
| How a test is written | `generation/prompt.py`, `generation/service.py`, `providers/mock/responder.py` |
| How a failure is explained | `sandbox/toolchain/plugins/testforge_pytest.py`, `toolchain/js/testforge-reporter.mjs`, `bugs/explain.py` |
| How tenants are isolated | `projects/access.py`, then `tests/integration/test_access.py` |

## 🔌 API

Everything the dashboard does is in the REST API under `/api/v1` ([OpenAPI](docs/api/openapi.yaml),
interactive at `/docs`). A CI job with a project API key:

```bash
curl -s -X POST "$TESTFORGE_URL/api/v1/projects/$PROJECT/imports/github?wait=120" \
  -H "Authorization: Bearer $TESTFORGE_API_KEY" -H 'content-type: application/json' \
  -d '{"repo": "owner/repo", "ref": "main"}'
curl -s -X POST "$TESTFORGE_URL/api/v1/projects/$PROJECT/runs?wait=600" \
  -H "Authorization: Bearer $TESTFORGE_API_KEY" -H 'content-type: application/json' \
  -d '{"kind": "all"}'
```

Or with the SDK and CLI ([sdk/python](sdk/python/README.md)):

```bash
testforge-cli generate --pull 12      # tests for exactly what pull request #12 changes
testforge-cli run                     # exits 1 unless every test passed
```

## ⚙️ Configuration

Configuration is environment only, validated at boot; production refuses demo secrets, a
local master key, local storage or insecure cookies. Every setting:
[configuration reference](docs/guides/configuration.md). The ones you will touch first:

| Variable | Default | Meaning |
| --- | --- | --- |
| `SANDBOX_URL`, `SANDBOX_SECRET` | `http://localhost:5635`, a dev value | Where the worker sends runs, and the secret that signs them |
| `RUN_CPU_S`, `RUN_WALL_S`, `RUN_MEMORY_MB`, `RUN_OUTPUT_BYTES` | 60, 120, 1024, 32000000 | A run's default budget (projects may lower or raise it up to the ceilings) |
| `GITHUB_API_URL` | `https://api.github.com` | GitHub or GitHub Enterprise |
| `KEY_MODE`, `KMS_KEY_ID` | `local` | How provider keys, tokens and secrets are sealed |
| `STORAGE`, `OBJECTS_BUCKET` | `local` | Where uploads, snapshots and reports live |

## ☁️ Deploy to AWS

`infra/terraform/envs/aws-dev` and `aws-prod` build the VPC, RDS PostgreSQL, ElastiCache,
S3, KMS, Secrets Manager, SES, ECR, ECS Fargate services behind an ALB with WAF, the sandbox
on EC2 instances of its own (its Docker daemon uses the sandbox seccomp profile, instance
metadata blocked, a task role with no policy, a security group that admits only the worker
and allows no egress), and CloudWatch alarms. Nothing in this repository has ever been
applied to a real account; the plan is applied, re-planned and destroyed against an emulator
on every `make tf-aws-on-floci`. [Deploy guide](docs/guides/deploy-aws.md)

## 🔐 Security model

| Concern | How it is handled |
| --- | --- |
| Running untrusted code | Only the sandbox runs code: nsjail per run, fresh user, PID, network, mount, IPC and UTS namespaces, uid 65534, read-only system directories, no `/proc`, a syscall filter refusing namespace, mount, ptrace, bpf and io_uring calls, in a container with every capability dropped |
| Network | A run has no interface but a loopback: the internet, the platform's services and cloud metadata are unreachable (tested by probes that try) |
| Credentials | The sandbox holds only its signing secret, which never reaches a run; provider keys, GitHub tokens and webhook secrets are sealed with AES-GCM or KMS, bound to their record, never returned |
| Runaway runs | CPU time, address space or heap, processes, output and wall clock limits; the run is stopped and the limit named |
| Planted outputs | A run's report and coverage files are read without following links, so a test cannot make the service hand back its own files |
| Analysis | Static only: imported code is parsed, never imported or executed, outside the sandbox |
| Tenants | Organization and project scoping in the access layer; another tenant's ids are 404, swept by a test |
| Audit | Append-only audit log; updates and deletes are rejected by a database trigger |

[Sandbox](docs/architecture/sandbox.md) · [Security](docs/architecture/security.md) ·
[Threat model](docs/architecture/threat-model.md) · Report vulnerabilities privately, sandbox
escapes first: see [SECURITY.md](SECURITY.md).

## 🧪 Testing

| Suite | What it proves | Run |
| --- | --- | --- |
| Unit (177 API, 85 web) | Analysis of Python and TypeScript, the assertion check (refusals and acceptances), prompts and the mock model, coverage parsing, failure explanations, pull request diffs, safe unpacking, the sandbox's signing, limit classification and output reading, every provider adapter, config guards, the OpenAPI drift check, web logic | `make test` |
| Integration (56) | The real API and worker against Postgres, Redis, the mock services and the real sandbox running the demo Python and TypeScript projects: A1 to A12, roles, tenant isolation, the SDK and CLI, the queue surviving a dead worker, a sandbox outage | `make test-integration` |
| Option matrix (4 runs) | The integration suite under local and KMS sealing, local disk and S3 storage | `make test-matrix` |
| Sandbox (15) | Inside the hardened sandbox image: real pytest and Vitest runs with coverage, no network (A3), nothing outside the workspace and planted links not followed (A4), CPU, wall clock, memory, output and process limits stopped and named (A5), the sandbox healthy afterwards | `make test-sandbox` |
| Browser (11) | Sign-in, imports from GitHub and ZIP, generation with refusals, a run with real coverage, a failure explained, the sandbox's refusals and limit, a pull request, API tests, the audit log, a viewer's read-only screens, theme and phone | `make e2e` |
| QA sweep (212 page views) | Every page for every role, light and dark, desktop and phone, with no console errors, failed requests or overflow (0 problems) | `make qa` |
| Infrastructure | `terraform validate` (3 environments), tflint (0 findings), checkov (411 passed, 0 failed), the aws-dev environment applied (208 resources), re-planned with nothing to add or replace, and destroyed on an emulator | `make tf-validate tf-lint tf-security tf-aws-on-floci` |

Unit and integration together cover 89% of the API. `make bench` on a laptop under load:
static analysis reads 53,000 lines of Python a second (TestForge's own 17,860-line source in
0.34 s); the assertion check handles 18,800 test files a second; writing and checking 28
tests for 20 units takes 2.9 ms besides the model; a one-test sandboxed run takes a median
0.46 s round trip and the demo project's suite with coverage 0.58 s (0.55 s of CPU, 56 MB).

[Testing guide](docs/guides/testing.md)

## 📖 Documentation

| Architecture | Guides |
| --- | --- |
| [High-level design](docs/architecture/HLD.md) | [Quickstart (local)](docs/guides/quickstart-local.md) |
| [Low-level design](docs/architecture/LLD.md) | [Local against real AWS](docs/guides/local-with-aws.md) |
| [Data model](docs/architecture/data-model.md) | [Deploy to AWS](docs/guides/deploy-aws.md) |
| [Sandbox](docs/architecture/sandbox.md) | [Configuration reference](docs/guides/configuration.md) |
| [Generation and the assertion check](docs/architecture/generation.md) | [Operations](docs/guides/operations.md) |
| [Analysis](docs/architecture/analysis.md) | [Testing](docs/guides/testing.md) · [Troubleshooting](docs/guides/troubleshooting.md) |
| [Security](docs/architecture/security.md) · [Threat model](docs/architecture/threat-model.md) | [Walkthrough](docs/guides/walkthrough.md) |
| [Decision records](docs/architecture/adr/) | [API reference (OpenAPI)](docs/api/openapi.yaml) |

## 🗺️ Roadmap

- More languages: Java, Go, PHP, C#, Ruby, Rust, C and C++
- Browser and visual regression tests (Playwright), performance and load tests (k6, Locust)
- Security testing: injection, XSS, CSRF and fuzzing
- Self-healing tests, an exploratory testing agent, bug reports turned into reproducing tests
- A flaky-test detector, risk-based prioritization and regression selection
- GitLab integration and a published GitHub Action
- microVM sandbox runners as a stronger isolation tier, and Kubernetes manifests

Have an idea? [Open a feature request](https://github.com/euron-sde-team/euron-open-testforge/issues/new/choose).

## ❓ FAQ

<details>
<summary><b>Does it run my code on the server?</b></summary>

Only in the sandbox service, never in the API or the worker, which only parse it. Each run
gets fresh namespaces with no network, no credentials and nothing of the platform mounted,
under CPU, memory, output and wall clock limits. See [the sandbox](docs/architecture/sandbox.md).
</details>

<details>
<summary><b>How do I know a generated test is worth keeping?</b></summary>

Every one passed the assertion check (a real assertion that can run and that calls the code
it tests), shows the assertions it makes and what it checks in words, and its expected values
come from the code and its documentation. You still accept each one; nothing runs as part of
your suite until you do.
</details>

<details>
<summary><b>Do I need a model key or an AWS account to try it?</b></summary>

No. A deterministic mock model writes the demo's tests from documented examples and raise
conditions, and `make up` runs S3, KMS and Secrets Manager on a local emulator provisioned by
the same Terraform as production.
</details>

<details>
<summary><b>My project's tests need packages. Will they run?</b></summary>

Runs have no network, so nothing is installed at run time. The sandbox image ships pytest,
pytest-cov, FastAPI, Flask, httpx, pydantic and requests for Python, and Vitest with Istanbul
for JavaScript and TypeScript. Other dependencies mean adding them to the image's pinned
toolchain ([sandbox.md](docs/architecture/sandbox.md)).
</details>

<details>
<summary><b>Can I use a model on my own servers?</b></summary>

Yes. Add an Ollama provider or any OpenAI-compatible endpoint under Settings, Model providers.
Private addresses are allowed; cloud metadata addresses are not.
</details>

## 🤝 Contributing, security and license

Contributions are welcome: read [CONTRIBUTING.md](CONTRIBUTING.md) and the
[code of conduct](CODE_OF_CONDUCT.md). Report security issues privately as described in
[SECURITY.md](SECURITY.md).

Released under the [MIT License](LICENSE). Copyright (c) 2026 ENGAGESPHERE TECHNOLOGY
PRIVATE LIMITED and the Euron Open TestForge contributors.

<p align="center">
  If Euron Open TestForge saves you time, <b><a href="https://github.com/euron-sde-team/euron-open-testforge/stargazers">⭐ star the repository</a></b>.
</p>
