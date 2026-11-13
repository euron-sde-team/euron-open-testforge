# Low-level design

How the code is laid out and how work moves through it. The big picture is in
[HLD.md](HLD.md); the sandbox in [sandbox.md](sandbox.md); generation and analysis in
[generation.md](generation.md) and [analysis.md](analysis.md).

## Package layout

```text
apps/api/src/testforge/
  core/          config (validated settings, production guard), container (process-wide
                 services), db, kv (Redis or in-process LRU, rate limits), pubsub (wake-ups),
                 sealing (AES-GCM or KMS), storage (disk or S3), net (SSRF checks), errors,
                 middleware (request id, security headers, body limit), security (argon2id,
                 sessions, API keys), mail, logs, tracing, tasks (periodic task registry)
  auth/ users/ orgs/ instance/ audit/     sign-in, people, organizations, settings, audit log
  projects/      projects, members, API keys, access.py (the Principal every route resolves)
  sources/       imports: archive.py (defensive unpacking), github.py (read-only REST),
                 service.py (create, fetch, analyze), the code_units table
  analysis/      static analysis: python.py (ast), jslex.py (masking lexer), javascript.py,
                 analyzer.py (whole snapshot, untested detection), model.py
  generation/    prompt.py (schema-aware prompts, answer parsing), checks.py (the assertion
                 check), templates.py (tests built from documented facts), service.py
  specs/         OpenAPI 3 documents and their operations
  pulls/         pull request imports: diff.py (changed lines, unit scoping), service.py
  runs/          test runs and test case results; service.py (create, execute, record)
  sandbox/       server.py (the sandbox service), jail.py (one nsjail run), classify.py
                 (which limit was crossed), runners.py + runners.yaml, protocol.py (request
                 signing), client.py (the worker's client), toolchain/ (plugins and pins)
  coverage/      parse.py (coverage.py JSON, Istanbul), service.py (store, project onto units)
  bugs/          explain.py (failure explanations from captured values), router.py
  providers/     model providers: adapters/ (openai, anthropic, gemini, ollama, mock),
                 gateway.py (one call with retries), service.py (sealed configuration)
  webhooks/      outbound deliveries and the inbound GitHub endpoint
  reports/ usage/ overview/ system/       exports, daily usage, the overview, health
  jobs/          models.py (the jobs table), queue.py (claim, lease, finish, reap),
                 handlers.py (what each job kind does), tasks.py (periodic tasks)
  demo/          the demo seed and the demo projects
  migrations/    Alembic
  main.py        create_app(): routers, middleware, lifespan
  worker.py      the worker and the scheduler loops
  cli.py         testforge serve | sandbox | worker | scheduler | migrate | revision |
                 create-admin | seed-demo | openapi
apps/api/src/mockai/   deterministic model providers, a GitHub API, a webhook receiver
sdk/python/            the euron-testforge SDK and the testforge-cli command
```

Dependencies point inward: router, service, models. A domain calls another domain's
service, never its tables; the worker's job handlers call the domain services
(`sources.process`, `generation.run`, `runs.execute` and `runs.record`).

## A request

1. `RequestContextMiddleware` assigns or accepts a request id, adds the security headers
   and logs one line. `BodySizeLimitMiddleware` refuses bodies over `MAX_BODY_BYTES` with
   413 before any route parses them; ZIP upload routes get the upload limit, and only for
   callers that present a valid session or API key.
2. `projects/access.py` resolves the caller into a `Principal`: an API key (one project,
   scopes `read`, `generate`, `execute`, `manage`) or a person (session cookie or bearer
   token) with a project role (`viewer` < `editor` < `admin`; organization owners and
   admins act as project admins). Route dependencies `Viewer`, `Editor`, `Generator`,
   `Executor` and `Admin` check the role or scope.
3. The service applies the rules. `AppError` subclasses become one JSON shape,
   `{"error": {"code", "message", "details"}}`, with a status per class.

## The container

`Container.build(settings)` creates, once per process, the database engine, the KV store
(Redis or `MemoryKV`), pub/sub (Redis or in-process), the outbound HTTP client (no
redirects followed, 100 connections), the sealer (local AES-GCM or KMS) and object storage
(disk or S3). Tests build their own.

## The job queue

`jobs` holds one row per piece of background work: `import`, `generate` or `run`, pointing
at its record by `ref_id`. The record keeps its own status for people; the job row carries
only the mechanics ([ADR-0005](adr/0005-postgres-job-queue.md)).

| Step | Code | What happens |
| --- | --- | --- |
| Enqueue | `queue.enqueue` | Adds the row in the caller's transaction, so a job exists exactly when its record does; `notify` publishes on `tf:queue` after commit |
| Claim | `queue.claim` | One `UPDATE ... WHERE id = (SELECT id ... status='queued' AND available_at <= now() ORDER BY available_at LIMIT 1 FOR UPDATE SKIP LOCKED) RETURNING *`: sets `running`, the lease owner (`<host>:<pid>#<n>`), `lease_expires_at = now() + LEASE_S`, and counts the attempt |
| Renew | `queue.renew` | A task in the worker renews the lease every `LEASE_S / 3` while the job runs (a long sandbox run outlives one lease) |
| Finish | `queue.finish` | `done` or `failed`, only `WHERE lease_owner = <me> AND status = 'running'`. If the reaper already handed the job to someone else, the write matches nothing and is dropped |
| Put back | `queue.retry_later` | Back to `queued` with a delay. `count=False` gives the attempt back: waiting for a busy sandbox never fails a job |
| Reap | `queue.reap` (scheduler) | Running jobs whose lease expired go back to `queued` with backoff `min(2^attempts, 30)` s, or fail after `MAX_ATTEMPTS`; a failed job's record is marked failed with a message a person can act on |
| Wake | `pubsub` | Idle workers wait on `tf:queue` or poll every `WORKER_POLL_INTERVAL_S`; a finished job publishes on `tf:job:<ref_id>` for an API request waiting with `?wait=` |

A handler that raises is retried with the same backoff until `MAX_ATTEMPTS`, then its
record is marked failed. SIGTERM stops claiming and gives running jobs 25 seconds; a hard
kill is safe because the lease runs out and another worker takes the job.

## The generation pipeline

`generation/service.py`:

1. `request` (API) resolves the import (the pull request's head import, a named import, or
   the project's current one), the units (explicit, the pull request's scoped units, or
   exported untested units up to `MAX_UNITS_PER_GENERATION`), the provider (named or the
   project default), and writes a `generations` row and a `generate` job.
2. `run` (worker) groups units by language and builds one prompt per language with
   `prompt.unit_payload` for each unit; each unit's source is cut to
   `max(400, PROMPT_SOURCE_CHARS / units)` characters.
3. `_call` sends `(system, user)` through `providers.gateway.complete` (retries on rate
   limits, overload and transport errors with jittered backoff, honouring `Retry-After`
   up to 30 s) at temperature 0 and 8000 output tokens, and adds tokens and model time to
   the generation.
4. `prompt.parse_answer` takes the JSON (bare, fenced, or the outermost braces) and turns
   every entry with a `code` string into a `ParsedTest`.
5. `checks.check(language, code, targets)` decides each test. The targets are the names
   of the unit the entry names (and its class), or every unit and class name when the
   entry names none; for API tests, the HTTP call names.
6. Accepted tests become `generated_tests` rows (`proposed`) with a file path
   (`tests/testforge/test_<slug>_<id6>.py` or `testforge/<slug>-<id6>.test.ts`), the
   assertions found and the model's plain-language description. Refused ones are kept as
   `{name, code, reason}` in `generations.rejections`.
7. Usage (`usage_daily`), metrics and a `generation.finished` audit row follow.

`POST /tests/{id}/regenerate` queues a new generation for the same unit (or operation)
and discards the old test.

## The run pipeline

`runs/service.py`:

1. `create` (API) picks the import, the tests (`generated`: the accepted ones or the ids
   given; `all`: accepted ones plus the suite), the language family, and the limits
   (`Settings.clamp_limits`: the project's values or the defaults, never above the
   ceilings), then writes a `test_runs` row and a `run` job.
2. `execute` (worker) loads the snapshot, adds each test's file at its `file_path`, and
   sends one `RunRequest` (job id, runner, base64 files, targets, limits) to the sandbox
   through `SandboxClient`. For kind `generated` the targets are the generated test files
   only; the project's own suite stays out.
3. `SandboxClient.run` signs the body, waits up to the wall limit plus 90 seconds, kills
   the run (`DELETE /v1/runs/<job>`) if the awaiting task is cancelled, and turns failures
   into `SandboxError(retryable, reason)`: `unreachable` and 5xx retry, `busy` (429) retries
   without counting the attempt, anything else fails the run.
4. `record` (worker) reads the cases from the runner's `report.json`; when the run was
   stopped before the report was written, from `events.jsonl` instead, adding the test that
   was running as an `error` that names the limit. Each failure is explained
   (`bugs/explain.py`) with the failing source line taken from the generated test or the
   snapshot. Generated tests get `last_outcome` and `last_run_id`.
5. The status is decided in this order: `error` when the sandbox itself failed;
   `limit_exceeded` when a limit was crossed; `failed` when any case failed or errored;
   `passed` when any passed; otherwise `error` ("the run finished without running any
   test").
6. Coverage is stored and projected (below), usage recorded, one `run.finished` audit row
   written (status, counts, limit, coverage, tests, import, source label, commit, who
   triggered it and how), and `run.finished` webhook deliveries queued, all in one commit.

## Coverage projection onto units

`coverage/parse.py` reads the tool's own report into one shape, paths relative to `/box`:

- **coverage.py** JSON: `executed_lines` are covered, `executed_lines | missing_lines` are
  the statements; branch totals from each file's summary.
- **Istanbul** `coverage-final.json`: a line is a statement when a statement starts on it,
  covered when that statement's hit count is above zero; branch totals from `b`.

`coverage/service.py` stores a `coverage_reports` row (totals and per-file coverage with
missing ranges) and then, for each code unit of the import whose file was measured,
computes `unit_percent`: the covered share of the tool's statements inside the unit's line
range **and** in the unit's own statement lines from analysis. Restricting to the body
leaves out the `def` or `class` line, which runs on import whether or not any test calls
the unit. A unit with no counted statement keeps its previous value. The untested-code
detector then reads `covered_percent` ([analysis.md](analysis.md)).

## Webhook delivery

Outbound (`webhooks/service.py`):

- `emit` writes one `webhook_deliveries` row per enabled webhook subscribed to the event,
  in the transaction that finished the run, so a delivery exists exactly when the event
  happened.
- The scheduler's `deliver_due` claims due rows with `FOR UPDATE SKIP LOCKED`, counts the
  attempt and pushes `next_attempt_at` forward (`min(30 * 2^(attempts-1), 3600)` seconds)
  before sending, so a crash never sends twice in a burst.
- Each send re-checks the URL (metadata addresses always refused; private ones unless
  `WEBHOOK_ALLOW_PRIVATE`), opens the sealed secret, and posts compact JSON with
  `X-TestForge-Event`, `X-TestForge-Delivery` and `X-TestForge-Signature:
  t=<unix>,v1=<hex HMAC-SHA256(secret, "<t>.<body>")>`. 2xx is delivered; anything else
  retries until `WEBHOOK_MAX_ATTEMPTS`, then `failed`.

Inbound (`POST /api/v1/hooks/github/{project_id}`): the body must carry GitHub's
`X-Hub-Signature-256` for the project's sealed webhook secret (an unknown project and a bad
signature get the same 401). `ping` answers `pong`; a `pull_request` event with action
`opened`, `reopened`, `synchronize` or `ready_for_review` imports and scopes the pull
request exactly as a person would (`source = webhook`); anything else is acknowledged and
ignored.

## The web app

`apps/web/src/`: `app/` holds routes only; `features/<domain>/` holds each domain's
components, hooks and API calls; `components/ui/` the shadcn primitives; `lib/` the API
client (types generated from `docs/api/openapi.yaml`), query keys and `STALE` times,
formatting. The browser talks only to the web app's origin.
