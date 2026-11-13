# Data model

PostgreSQL 16, SQLAlchemy 2 models per domain, one Alembic revision
(`migrations/versions/242a30469fbc_initial_schema.py`). Timestamps are timezone aware.
Every project-scoped table carries `project_id`, and every query that reads one filters on
it; a row of another project is never found, so it answers 404. Blobs never live in a row:
uploads, snapshots and reports are in object storage and rows keep the key.

## People, organizations and access

| Table | Holds | Notes |
| --- | --- | --- |
| `users` | email (unique), name, argon2id hash, role (`user` or instance `admin`), disabled, last login, failed logins, locked until, session version | Changing a password bumps the session version and ends every other session |
| `revoked_sessions` | signed-out session ids (`jti`) until they would have expired | In Postgres, never a cache, so eviction cannot bring a session back |
| `organizations` | name, slug (unique), creator | |
| `org_members` | (org, user), role `member`, `admin` or `owner` | Owners and admins act as admins of every project in the organization |
| `projects` | organization, name, slug (unique per organization), description, GitHub repository, sealed GitHub token, sealed GitHub webhook secret, run limit overrides (`run_cpu_s`, `run_wall_s`, `run_memory_mb`, `run_output_bytes`, null for the defaults), current import, creator | Limits are clamped to the instance ceilings when a run is created |
| `project_members` | (project, user), role `viewer`, `editor` or `admin` | |
| `api_keys` | project, name, prefix (unique), peppered HMAC of the secret, scopes (`read`, `generate`, `execute`, `manage`), last used, revoked, creator | The secret is shown once; a leaked table cannot be turned into keys without `API_KEY_PEPPER` |
| `instance_settings` | one row (`id = 1`): site name, whether sign-up is open | |
| `audit_log` | time, actor id and email, action, target type and id, details (JSONB), IP, org and project | Append-only: a trigger refuses `UPDATE` and `DELETE`, and retention never touches it |

## Model providers

| Table | Holds | Notes |
| --- | --- | --- |
| `model_providers` | project, name (unique per project), kind (`openai`, `anthropic`, `gemini`, `ollama`, `openai_compatible`, `mock`), base URL, model, sealed API key, sealed extra headers, enabled, default, timeout, last connection test and its result | Keys are sealed with an encryption context bound to the record and never returned |

## Source and analysis

| Table | Holds | Notes |
| --- | --- | --- |
| `source_imports` | project, kind (`zip`, `github`, `pull_request`), status (`pending`, `analyzing`, `ready`, `failed`), label, repository, ref, commit SHA, upload key (until unpacked), snapshot key, size, file count, languages, frameworks, test frameworks, summary (unit counts, test files, dependencies, application objects, parse errors, skipped files, untested count), error, analysis time | Index `(project_id, created_at)`. The snapshot at `snapshots/<project>/<import>.zip` never changes |
| `code_units` | import, project, kind (`function`, `method`, `class`, `route`), language, name, qualified name, file, module, start and end line, signature, docstring, source (up to 8000 characters), details (parameters, return annotation, documented examples, raises with conditions, statement lines, class name, route, constructor), exported, async, statement count, referenced by tests, covered percent | Index `(import_id, file)`. Replaced as a whole when an import is analyzed again |
| `api_specs` | project, title, version, the OpenAPI 3 document (JSONB), its operations (key, method, path, parameters, request body schema, responses), operation count, creator | Limited to `MAX_SPEC_BYTES` |
| `pull_request_imports` | project, repository, number, title, author, base ref and SHA, head ref and SHA, status, the head commit's import, changed files (path, status, additions, deletions, previous path, changed head-side line ranges), scoped unit ids, source (`manual` or `webhook`), error | Unique `(project_id, repo, number, head_sha)`: importing the same head twice returns the first |

## Generation

| Table | Holds | Notes |
| --- | --- | --- |
| `generations` | project, import, status (`queued`, `running`, `done`, `failed`), kinds, unit ids, OpenAPI document, pull request, extra instructions, provider id, kind and model, accepted and rejected counts, rejections (`[{name, code, reason}]`), operations covered, input and output tokens, model time, error code and message, who asked, finished time | Index `(project_id, created_at)`. A refused test exists only here, as a name and a reason |
| `generated_tests` | project, import, generation, unit, operation (`GET /items/{id}`), kind (`unit`, `edge`, `negative`, `api`), language, framework, name, file path in the workspace, code, description, the assertions the check found (`[{test, line, text}]`), status (`proposed`, `accepted`, `discarded`), last outcome and run, reviewer | Index `(project_id, status)`. Only tests that passed the assertion check are ever stored |

## Runs and coverage

| Table | Holds | Notes |
| --- | --- | --- |
| `test_runs` | project, import, kind (`generated`, `project`, `all`), language, framework, status (`queued`, `running`, `passed`, `failed`, `error`, `limit_exceeded`), test ids, limits (`cpu_s`, `wall_s`, `memory_mb`, `output_bytes`), limit exceeded (`cpu`, `memory`, `wall_clock`, `output`, `processes`), exit code, signal, CPU time, wall time, peak memory, output bytes, passed, failed, errors, skipped, coverage percent, stdout and stderr tails, message, trigger, who triggered it, created, started, finished | Index `(project_id, created_at)`; check constraints on kind, status and limit |
| `test_case_results` | run, generated test (when the case came from one), node id, file, name, outcome (`passed`, `failed`, `error`, `skipped`), duration, message, failure (kind, operator, actual, expected, line, expression, explanation, and the limit for a test stopped by one) | The failure is computed from the values captured in the same execution |
| `coverage_reports` | project, run, import, tool (`coverage.py` or `istanbul`), lines total and covered, line percent, branches total and covered, branch percent, files (path, totals, percent, missing ranges) | Index `(project_id, created_at)` for the trend |

## Jobs, webhooks, reports, usage

| Table | Holds | Notes |
| --- | --- | --- |
| `jobs` | kind (`import`, `generate`, `run`), project, ref id, status (`queued`, `running`, `done`, `failed`), attempts, available at, lease owner, lease expiry, error, created, finished | Partial indexes `ix_jobs_claim (available_at) WHERE status='queued'` and `ix_jobs_lease (lease_expires_at) WHERE status='running'` |
| `webhooks` | project, name, URL, events, sealed secret, enabled, creator | The secret is shown once at creation |
| `webhook_deliveries` | webhook, event, payload, status (`pending`, `delivered`, `failed`), attempts, next attempt, last status code and error, created, delivered | Indexed on due pending rows for the scheduler |
| `reports` | project, scope (`run` or `project`), run, format (`csv` or `html`), title, object key, size, creator, created | The file is in object storage; retention removes both |
| `usage_daily` | (project, day, model): generations, tests accepted and rejected, runs, failed runs, sandbox time, input and output tokens | Pre-aggregated per day, so usage views never read every run |

## Retention

The scheduler's `retention` task deletes runs (with their cases and coverage by cascade),
finished jobs and exported reports (row and object) older than `RETENTION_DAYS`. The audit
log is never purged.
