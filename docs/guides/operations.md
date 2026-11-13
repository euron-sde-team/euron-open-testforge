# Operations

## Health

| Endpoint | Meaning |
| --- | --- |
| `GET /healthz` (api) | The process is up |
| `GET /readyz` (api) | Postgres answers (503 otherwise); Redis is probed when configured and reported |
| `GET /api/v1/system` (instance admins) | Version, environment, storage, key mode, cache and mail backends, whether Redis answers, the job queue (`queued`, `running`, `oldest_queued_s`), counts of organizations, projects, users, imports, generated tests and runs, and whether the sandbox answered the API's health probe (the API is not on the sandbox's network in Compose or on AWS, so read the worker's sandbox metrics for the sandbox's real state) |
| `GET /healthz` (sandbox) | The service is up, nsjail is present, the runners it offers |
| `/metrics` | Prometheus, on the api (port 8080), the worker (`WORKER_METRICS_PORT`, 9464) and the sandbox (8080) |

In Compose the worker's health check is its metrics endpoint; the sandbox's is its
`/healthz`.

## Metrics

| Metric | Where | Labels |
| --- | --- | --- |
| `testforge_jobs_total`, `testforge_job_seconds` | worker | kind (`import`, `generate`, `run`), status |
| `testforge_queue_depth` | scheduler | status (`queued`, `running`, `oldest_wait_s`) |
| `testforge_analysis_seconds` | worker | |
| `testforge_generated_tests_total` | worker | outcome (`accepted`, `rejected_<code>`) |
| `testforge_runs_total` | worker | status |
| `testforge_sandbox_limits_total` | worker | limit (`cpu`, `memory`, `wall_clock`, `output`, `processes`) |
| `testforge_sandbox_seconds` | worker | wall time of a sandbox call, as the worker saw it |
| `testforge_sandbox_failures_total` | worker | reason (`unreachable`, `busy`, `refused`, `launch`) |
| `testforge_model_calls_total`, `testforge_model_latency_seconds`, `testforge_tokens_total` | worker (generations) | provider kind and outcome; token direction |
| `testforge_webhook_deliveries_total` | scheduler | outcome (`delivered`, `retry`, `failed`) |
| `testforge_dependency_errors_total` | every role | dependency and operation (a Redis error counted as a cache miss or a limiter pass) |
| `testforge_sandbox_runs_total`, `testforge_sandbox_run_seconds` | sandbox | runner, outcome (`completed`, a limit, or `error`) |

## Logs

Every role writes one JSON object per line to stdout: `level`, `msg`, the logger, a
request id on the API, and the extra fields at the top level. Tokens in URLs are redacted.
Locally: `make logs SERVICE=api` (or `worker`, `scheduler`, `sandbox`, `web`, `mockai`,
`floci`). On AWS each app has a log group `/testforge/<prefix>/<app>`.

Two lines are what the CloudWatch alarms read; keep their `msg` exactly as is:

| Line | Written by | Fields | CloudWatch |
| --- | --- | --- | --- |
| `{"msg": "job queue", "queued": N, "running": N, "oldest_wait_s": N}` | the scheduler, once per tick (`TASK_INTERVAL_S`) | the queue depth | `JobQueueQueued` from `$.queued`; the alarm fires when it stays above `queue_queued_threshold` (50) for 15 minutes |
| `{"msg": "sandbox failure", "reason": "...", "run": "<id>"}` | the worker, once per sandbox call that failed for a reason other than the tests | `reason`: `unreachable`, `busy`, `refused`, `launch` | `SandboxFailures`; the alarm fires above `sandbox_failure_threshold` (5) per 5 minutes |

The sandbox service's own `error` and `critical` lines (for example "nsjail could not start
the run") become `SandboxErrors`, with an alarm on any occurrence. The sandbox also logs
`run done` with the runner, exit code, limit and wall time for every run.

## When runs fail for a reason other than the tests

A run whose status is `error` failed in the sandbox, not in the tests. The run's message
and the worker's `sandbox failure` lines say why:

| Reason | Cause | What happens | Fix |
| --- | --- | --- | --- |
| `busy` | Every sandbox slot was taken for 30 s | The job goes back to the queue after 5 s; the attempt is not counted | Add sandbox replicas if it persists |
| `unreachable` | The worker cannot connect to `SANDBOX_URL` | Retried after 15 s, counted; after `MAX_ATTEMPTS` the run fails with the reason | `make logs SERVICE=sandbox`; on AWS check the sandbox service and its hosts |
| `refused` | The sandbox answered 4xx (a bad signature: `SANDBOX_SECRET` differs between worker and sandbox) or 5xx | 4xx fails the run; 5xx is retried | Give both the same secret |
| `launch` | nsjail could not start the run: the container lacks the sandbox seccomp profile, or the host forbids unprivileged user namespaces | The run is recorded as `error` | Run the sandbox with `seccomp=infra/docker/sandbox-seccomp.json` (Compose and the Terraform do); see [troubleshooting](troubleshooting.md) |

A run that crossed a limit is not a failure of the sandbox: its status is
`limit_exceeded` and the message names the limit.

## Scaling the sandbox

A sandbox process runs one test run at a time (`SANDBOX_CONCURRENCY=1`), because
`RLIMIT_NPROC` counts per uid and every jail shares one. Throughput is roughly the number
of sandbox replicas divided by the average run time. Signs you need more: `busy` sandbox
failures, `testforge_queue_depth{status="queued"}` above zero for long, or the queue alarm.

- **Locally**: `docker compose --env-file deploy/compose/.env -f deploy/compose/compose.yaml
  -f deploy/compose/compose.floci.yaml up -d --scale sandbox=3` (each replica can use 2
  CPUs and 3 GB). The worker reaches them through the service name.
- **On AWS**: raise `sandbox_desired_count` (one task per host); with the module's
  `max_count` above `desired_count`, CPU target tracking adds tasks and the capacity
  provider adds hosts. A run cut short by a deploy or scale-in is retried by the worker.

Raise `WORKER_CONCURRENCY` or the worker count together with the sandbox, or the sandbox
waits for the worker. Generations do not use the sandbox; they are bounded by the model.

## Backups

Postgres holds every record and the job queue; object storage holds uploads, snapshots and
reports.

- **Locally**: `docker compose --env-file deploy/compose/.env -f deploy/compose/compose.yaml
  -f deploy/compose/compose.floci.yaml exec postgres pg_dump -U testforge -Fc testforge >
  testforge.dump` takes a consistent dump while the app keeps serving. The objects live in
  Floci's bucket `testforge-local-objects` (or the `objects` volume with `STORAGE=local`).
- **On AWS**: RDS automated backups and snapshots; the objects bucket is SSE-KMS
  encrypted. Restore a snapshot into a new instance, point `DATABASE_URL` at it, and run
  the `migrate` task.

## Rotating secrets

| Secret | Effect of rotating |
| --- | --- |
| `SESSION_SECRET` | Everyone is signed out |
| `API_KEY_PEPPER` | Every API key stops working: issue new ones |
| `SANDBOX_SECRET` | Update the worker and the sandbox together; do it after any suspected sandbox escape |
| `LOCAL_MASTER_KEY` | Sealed provider keys, GitHub tokens and webhook secrets can no longer be opened: enter them again (use `KEY_MODE=kms` in production) |

## Retention

The scheduler's `retention` task deletes runs (with their cases and coverage), finished
jobs and exported reports older than `RETENTION_DAYS` (90). Imports, snapshots, generated
tests and the audit log are kept; the audit log is append-only.

## Stuck work

A job whose worker died is reclaimed when its lease (`LEASE_S`, 120 s) runs out: back to
the queue with backoff, or failed after `MAX_ATTEMPTS` with a message on the import,
generation or run ("The worker handling this stopped 3 times"). The queue itself is
readable with SQL: `SELECT kind, status, attempts, error FROM jobs ORDER BY created_at DESC
LIMIT 20`.
