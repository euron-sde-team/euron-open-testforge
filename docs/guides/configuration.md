# Configuration

Every setting is an environment variable, read once at start and validated
(`apps/api/src/testforge/core/config.py`). Names are case-insensitive; the tables use the
upper-case form. The api, worker, scheduler and sandbox share one `Settings` class, but
each role is given only what it needs: the sandbox gets `SANDBOX_SECRET`, `LOG_LEVEL` and
`SANDBOX_CONCURRENCY` and nothing else, in Compose and on ECS.

With `ENVIRONMENT=production` every role refuses to start when `SESSION_SECRET`,
`API_KEY_PEPPER` or `SANDBOX_SECRET` is a demo value or shorter than 32 characters, when
any two of them are equal, when `KEY_MODE=local` and `LOCAL_MASTER_KEY` is weak, when
`COOKIE_SECURE` is false, when `MAIL_BACKEND=log`, when `STORAGE=local`, or when
`AWS_ENDPOINT_URL` is set with `TESTFORGE_CLOUD=aws`.

## Settings

### Runtime, database, cache

| Variable | Default | Meaning |
| --- | --- | --- |
| `ENVIRONMENT` | `development` | `development`, `test` or `production` (production enables the guard above) |
| `LOG_LEVEL` | `INFO` | Log level |
| `TESTFORGE_CLOUD` | `local` | `local`, `floci` or `aws`: where AWS calls go (informational, plus the guard above) |
| `DATABASE_URL` | `postgresql+asyncpg://testforge:testforge@localhost:5642/testforge` | Postgres (asyncpg driver). Holds every record and the job queue |
| `DB_POOL_SIZE`, `DB_MAX_OVERFLOW` | `10`, `20` | Connection pool per process |
| `REDIS_URL` | empty | Optional: rate limits, the snapshot file index cache and pub/sub wake-ups. Without it each process keeps its own (exact for one replica) |
| `MEMORY_CACHE_MAX_BYTES` | `64000000` | Byte budget of the in-process cache used when `REDIS_URL` is empty (at least 1 MB) |

### Sessions, API keys, links

| Variable | Default | Meaning |
| --- | --- | --- |
| `SESSION_SECRET` | dev value | Signs session tokens. At least 32 random characters in production |
| `API_KEY_PEPPER` | dev value | HMAC key for API key secrets (only the HMAC is stored) |
| `SESSION_TTL_HOURS` | `12` | Session lifetime |
| `COOKIE_SECURE` | `false` | Secure flag on the `tf_session` cookie; must be true in production |
| `CORS_ORIGINS` | `http://localhost:5610` | Comma separated origins allowed to call the API from a browser |
| `PUBLIC_URL` | `http://localhost:5610` | Where people open the app; used in links in mail, webhook payloads and HTML reports |

### Sealing, AWS and storage

| Variable | Default | Meaning |
| --- | --- | --- |
| `KEY_MODE` | `local` | `local` seals provider keys, GitHub tokens and webhook secrets with AES-256-GCM and `LOCAL_MASTER_KEY`; `kms` uses KMS with a per-record encryption context |
| `LOCAL_MASTER_KEY` | dev value | The local sealing key (required in production when `KEY_MODE=local`) |
| `KMS_KEY_ID` | `alias/testforge-local` | The KMS key for `KEY_MODE=kms` |
| `AWS_REGION` | `us-east-1` | AWS region |
| `AWS_ENDPOINT_URL` | unset | Set to the emulator (`http://floci:4566`) locally; unset on AWS |
| `S3_FORCE_PATH_STYLE` | `false` | Path-style S3 URLs (needed for the emulator) |
| `STORAGE` | `local` | `local` (disk under `LOCAL_STORAGE_DIR`) or `s3` (`OBJECTS_BUCKET`) for uploads, snapshots and reports. Production requires `s3`, since replicas share snapshots |
| `OBJECTS_BUCKET` | `testforge-local-objects` | The bucket |
| `LOCAL_STORAGE_DIR` | `./.data/objects` | The directory for `STORAGE=local` |

### Mail

| Variable | Default | Meaning |
| --- | --- | --- |
| `MAIL_BACKEND` | `log` | `log` (nothing leaves the process), `smtp` (Mailpit locally, any relay) or `ses` |
| `MAIL_FROM` | `TestForge <testforge@testforge.local>` | Sender of member notices |
| `SMTP_HOST`, `SMTP_PORT` | `localhost`, `1025` | For `MAIL_BACKEND=smtp` (Compose points them at `mailpit:1025`) |

### Model providers and GitHub

| Variable | Default | Meaning |
| --- | --- | --- |
| `PROVIDER_ALLOW_PRIVATE` | `true` | Allow model provider base URLs on private addresses (a local Ollama or vLLM). Metadata addresses are always refused. Providers themselves are configured per project in the app |
| `MODEL_TIMEOUT_S` | `120` | Ceiling on a provider's own timeout setting |
| `GITHUB_API_URL` | `https://api.github.com` | The GitHub (or GitHub Enterprise) REST API. Compose points it at the mock GitHub for the demo |
| `GITHUB_ALLOW_PRIVATE` | `false` | Allow `GITHUB_API_URL` to resolve to a private address (GitHub Enterprise inside the network, the mock) |
| `GITHUB_TIMEOUT_S` | `60` | Timeout for each GitHub request and archive download |

### Imports and generation

| Variable | Default | Meaning |
| --- | --- | --- |
| `MAX_UPLOAD_BYTES` | `25000000` | Largest ZIP upload (and the request body limit on the upload route). GitHub archives may be up to four times this |
| `MAX_SNAPSHOT_BYTES` | `50000000` | Total uncompressed text kept from one archive; unpacking stops at it |
| `MAX_SNAPSHOT_FILES` | `5000` | Files kept from one archive |
| `MAX_FILE_BYTES` | `1000000` | Largest single file kept; larger ones are skipped and listed |
| `MAX_SPEC_BYTES` | `2000000` | Largest OpenAPI document |
| `MAX_UNITS_PER_GENERATION` | `25` | Units one generation writes tests for |
| `PROMPT_SOURCE_CHARS` | `24000` | Characters of source in one prompt, shared across its units (each gets at least 400) |
| `GENERATE_RPM`, `RUN_RPM` | `30`, `60` | Generations and runs per project per minute |
| `MAX_BODY_BYTES` | `2000000` | Request body limit everywhere except the ZIP upload route |
| `WORK_DIR` | `./.data/work` | Scratch space for the api, worker and scheduler, mounted writable in Compose and on ECS (their root filesystems are read-only) |

### Runs and the sandbox

| Variable | Default | Meaning |
| --- | --- | --- |
| `SANDBOX_URL` | `http://localhost:5635` | Where the worker reaches the sandbox service (`http://sandbox:8080` in Compose, the Cloud Map name on AWS) |
| `SANDBOX_SECRET` | dev value | HMAC key signing every worker to sandbox request. Shared by the worker and the sandbox; must differ from the other secrets |
| `RUN_CPU_S` | `60` | Default CPU time of one run |
| `RUN_WALL_S` | `120` | Default wall clock of one run |
| `RUN_MEMORY_MB` | `1024` | Default memory of one run |
| `RUN_OUTPUT_BYTES` | `32000000` | Default output limit of one run: no file the run writes may grow past it (`RLIMIT_FSIZE`, rounded up to whole MB), and stdout or stderr reaching it stops the run as `output`. The coverage report is one of those files, so the default leaves room for a large project's `coverage.json` |
| `RUN_CPU_CEILING_S`, `RUN_WALL_CEILING_S` | `600`, `900` | The most a project may set for CPU and wall clock |
| `RUN_MEMORY_CEILING_MB` | `4096` | The most a project may set for memory. Keep it below the sandbox container's memory limit |
| `RUN_OUTPUT_CEILING_BYTES` | `100000000` | The most a project may set for output |
| `MAX_WORKSPACE_BYTES` | `40000000` | The most a run may send to the sandbox (the snapshot plus the generated tests); a larger run fails with `workspace_too_large` before it is sent. The sandbox service refuses anything over 60 MB on its own side as well |

A project's own limits (Settings in the app, or `PATCH /projects/{id}` with `run_cpu_s`,
`run_wall_s`, `run_memory_mb`, `run_output_bytes`) replace the defaults and are clamped to
the ceilings when a run is created.

### Sandbox service only (`testforge sandbox`)

| Variable | Default | Meaning |
| --- | --- | --- |
| `NSJAIL_PATH` | `/usr/local/bin/nsjail` | The nsjail binary |
| `SANDBOX_WORK_DIR` | `/tmp/testforge-sandbox` | Where each run's workspace is built (a tmpfs owned by the service user) |
| `TOOLCHAIN_DIR` | `/opt/toolchain` | The read-only test toolchain every run sees |
| `SANDBOX_CONCURRENCY` | `1` | Runs at once per sandbox process. Keep 1: `RLIMIT_NPROC` counts per uid and every jail maps to the same uid; scale with more sandbox replicas |

### Worker, scheduler, webhooks, retention, telemetry

| Variable | Default | Meaning |
| --- | --- | --- |
| `WORKER_CONCURRENCY` | `4` | Jobs one worker runs at once |
| `LEASE_S` | `120` | A job's lease; renewed every third of it while the job runs. A job whose worker stops renewing is reaped after this |
| `MAX_ATTEMPTS` | `3` | Claims (or counted retries) before a job fails for good |
| `WORKER_POLL_INTERVAL_S` | `2` | How often an idle worker looks for jobs when no wake-up arrives |
| `TASK_INTERVAL_S` | `10` | Scheduler tick when idle |
| `WORKER_METRICS_PORT` | `9464` | Prometheus port of the worker and scheduler (0 disables; Compose sets 0 for the scheduler) |
| `WEBHOOK_MAX_ATTEMPTS` | `6` | Delivery attempts before a webhook delivery fails |
| `WEBHOOK_TIMEOUT_S` | `10` | Timeout of one delivery |
| `WEBHOOK_ALLOW_PRIVATE` | `false` | Allow webhook URLs on private addresses (a CI server inside the network). Metadata and link-local addresses are refused either way |
| `RETENTION_DAYS` | `90` | Runs, finished jobs and exported reports older than this are purged; the audit log never is |
| `OTEL_ENABLED` | `false` | OpenTelemetry tracing |

## Outside `Settings`

| Variable | Read by | Default | Meaning |
| --- | --- | --- | --- |
| `PORT` | `testforge serve`, `testforge sandbox` | `8080` | Listen port in the container |
| `FORWARDED_ALLOW_IPS` | `testforge serve` | `127.0.0.1` | Proxies whose `X-Forwarded-For` is trusted (`*` on the Compose network, the VPC CIDR on AWS) |
| `TESTFORGE_ADMIN_PASSWORD` | `testforge create-admin` | prompt | Password for the admin being created or reset |
| `TESTFORGE_DEMO_PASSWORD` | `testforge seed-demo` | required | Password of every demo account (`make env` generates it) |
| `TESTFORGE_DEMO_API_URL` | `testforge seed-demo` | `http://api:8080` | The API the seed drives |
| `TESTFORGE_DEMO_MOCK_URL` | `testforge seed-demo` | `http://mockai:5650` | The mock services (GitHub, webhook receiver) |
| `API_INTERNAL_URL` | the web app | | Where the web container reaches the API (`http://api:8080` in Compose) |

The Python SDK and `testforge-cli` read `TESTFORGE_URL`, `TESTFORGE_API_KEY` and, for a
session instead of a key, `TESTFORGE_PROJECT_ID` (`sdk/python/README.md`).

## Local stack (`deploy/compose/.env`)

`make env` writes the secrets once (`SESSION_SECRET`, `API_KEY_PEPPER`, `LOCAL_MASTER_KEY`,
`SANDBOX_SECRET`, `TESTFORGE_DEMO_PASSWORD`) and never overwrites them. Optional
overrides:

| Variable | Default | Meaning |
| --- | --- | --- |
| `TESTFORGE_WEB_PORT` | `5610` | Web app |
| `TESTFORGE_API_PORT` | `5630` | API |
| `TESTFORGE_SANDBOX_PORT` | `5635` | The integration suite's sandbox (`sandbox-test`, `make test-integration`); the stack's own sandbox publishes no port |
| `TESTFORGE_MAILPIT_PORT` | `5625` | Mailpit web UI |
| `TESTFORGE_MOCKAI_PORT` | `5650` | The mock services (model providers, GitHub, webhook receiver) |
| `TESTFORGE_PG_PORT`, `TESTFORGE_REDIS_PORT`, `TESTFORGE_FLOCI_PORT` | `5642`, `5679`, `5666` | Postgres, Redis, Floci |
| `TESTFORGE_WORKER_CONCURRENCY` | `4` | Jobs the worker runs at once |
| `TESTFORGE_GITHUB_API_URL` | the mock GitHub | Set `https://api.github.com` to import real repositories |
| `TESTFORGE_APT_MIRROR` | empty | A faster Debian mirror for building the sandbox image: an `http` URL ending in `/debian` that also serves `<url>-security` |
| `TESTFORGE_LOG_LEVEL` | `INFO` | Log level for every service |

`make tf-aws-on-floci` uses its own throwaway Floci on port 5696 (`TF_FLOCI_PORT`).

## Runners

`apps/api/src/testforge/sandbox/runners.yaml` defines each test runner: the command, the
coverage arguments and output file, the coverage tool, the run's environment, the memory
mode (`address` or `rss`) with its overhead, and the process limit. Adding one means
installing its toolchain in the sandbox image under `/opt/toolchain` and adding an entry
([sandbox.md](../architecture/sandbox.md#the-runners)).
