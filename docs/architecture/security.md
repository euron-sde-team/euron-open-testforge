# Security

What TestForge protects, and how. The sandbox has its own document:
[sandbox.md](sandbox.md). The attacks considered are in [threat-model.md](threat-model.md).

## Assets

| Asset | Why it matters |
| --- | --- |
| The platform's hosts and network | TestForge executes uploaded projects and model-written tests by design |
| Source code | A project's code is often private; a run of one project must never see another's |
| Credentials | `SESSION_SECRET`, `API_KEY_PEPPER`, `SANDBOX_SECRET`, the master key or KMS key, model provider keys, GitHub tokens, webhook secrets, the database and cache URLs |
| Test results and the audit trail | Developers decide what to merge on them; the audit log says who ran what, on which code |
| Accounts, sessions and API keys | Editors import code, spend model tokens and start runs; admins manage keys and providers |

## Controls

### Executing code
- Every execution, of a generated test, an uploaded project or its own suite, happens in
  the sandbox service: an unprivileged container, nsjail per run with fresh user, PID,
  network, mount, IPC and UTS namespaces, a syscall filter, rlimits, no network, no
  `/proc`, a read-only toolchain and a private workspace ([sandbox.md](sandbox.md)).
- The sandbox holds only `SANDBOX_SECRET`; no database, cache, storage, provider or GitHub
  credential is ever given to it. In Compose it sits on an internal network shared with
  the worker alone; on AWS its security group admits only the worker and has no egress.
- Only signed requests (HMAC-SHA256 over a timestamp and the body, five minutes of skew)
  start or stop a run.
- Results are read back with `O_NOFOLLOW` and size caps, so a run cannot make the service
  hand back a file it should not.
- One run per sandbox process, so per-uid limits are exact and runs never share a jail.

### Never executing code elsewhere
- Imports download GitHub's tarball for one commit; nothing is cloned and no git hook,
  install script or build step runs ([ADR-0006](adr/0006-github-archives-not-git-clone.md)).
- Archives are unpacked into memory defensively: no absolute paths, `..`, links or
  devices; file count, file size and total size capped while reading (ZIP bombs stop at the
  cap).
- Analysis parses source with `ast` and a masking lexer; nothing is imported or evaluated
  ([ADR-0004](adr/0004-static-analysis-never-executes-code.md)).
- The assertion check reads generated tests; it never runs them
  ([ADR-0003](adr/0003-assertion-check-before-a-test-is-shown.md)).

### Tenancy and authorization
- Every project route resolves a `Principal` first (`projects/access.py`) and every query
  filters on that project. A project the caller cannot see, an API key for another project,
  and a missing project all answer **404**, never 403, so existence does not leak.
- Project roles: `viewer` reads; `editor` also imports, generates, reviews and runs;
  `admin` also manages members, API keys, model providers, webhooks and the GitHub
  connection. Organization owners and admins act as project admins.
- API keys belong to one project and carry scopes: `read`, `generate` (a model is
  called), `execute` (the sandbox), `manage` (imports, specs, test review, webhooks).
  Keys are `tfk_<prefix>_<secret>`; only a peppered HMAC of the secret is stored.

### Accounts and sessions
- Passwords hashed with argon2id; an unknown email costs the same time as a known one.
- Sign-in throttled per IP (20 per minute) and locked per account for 15 minutes after 5
  failures (in Postgres, so it holds across replicas).
- Sessions are signed tokens in an HttpOnly cookie (`tf_session`, Secure in production)
  or a bearer header. Signing out records the session id in `revoked_sessions` until it
  would have expired; changing a password bumps the session version, ending every other
  session.
- Cookie-authenticated mutations need `X-TF-CSRF: 1`, which a cross-site page cannot add
  without a CORS preflight the allowlist refuses.

### Outbound requests
- Model provider base URLs, GitHub's API URL and webhook URLs are resolved at call time
  and refused when any address is a metadata address (including numeric, hex, octal and
  trailing-dot spellings of 169.254.169.254, and AWS's IPv6 metadata address). Private
  addresses are refused for GitHub (`GITHUB_ALLOW_PRIVATE`) and webhooks
  (`WEBHOOK_ALLOW_PRIVATE`) unless allowed; allowed by default for model providers
  (`PROVIDER_ALLOW_PRIVATE`), since a local Ollama or vLLM is normal.
- The outbound HTTP client follows no redirects; GitHub archive redirects are followed only
  to GitHub's own archive host or the configured API host.
- Inbound GitHub webhooks must carry a valid `X-Hub-Signature-256` for the project's
  sealed secret; outbound deliveries are signed with `X-TestForge-Signature`.

### Input and output
- Request bodies are capped before parsing (`MAX_BODY_BYTES`); only the ZIP upload route
  accepts more (`MAX_UPLOAD_BYTES`), and only from a caller with a valid session or a
  well-formed API key.
- Generations and runs are rate limited per project (`GENERATE_RPM`, `RUN_RPM`) and answer
  429 with `Retry-After`. A Redis outage never blocks work: the limiter fails open and the
  error is counted.
- CSV exports neutralise cells starting with `=`, `+`, `-`, `@`, tab or carriage return.
- Downloaded HTML reports carry `Content-Security-Policy: default-src 'none';
  style-src 'unsafe-inline'; sandbox`, so a report never runs script in the API's origin.
- Errors are one JSON shape and never include stack traces.

### Headers
API: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy:
no-referrer`, `Cross-Origin-Opener-Policy: same-origin`, a restrictive
`Permissions-Policy`, and a request id on every response.

### Secrets and configuration
- Secrets come only from the environment (Secrets Manager on AWS, injected per container:
  the sandbox's execution role reads only its own secret).
- Provider keys and headers, GitHub tokens and webhook secrets are sealed in the database
  (AES-256-GCM with a key derived from `LOCAL_MASTER_KEY`, or KMS on AWS) with an
  encryption context bound to the record, so a sealed value copied to another row fails to
  open. They are opened only when used and never returned by the API.
- With `ENVIRONMENT=production` every role refuses to start with demo or short secrets
  (fewer than 32 characters), equal secrets, a missing master key in local key mode,
  `COOKIE_SECURE` off, `MAIL_BACKEND=log`, `STORAGE=local`, or an `AWS_ENDPOINT_URL` with
  `TESTFORGE_CLOUD=aws`.
- `make sanitize` fails the build on credentials, cloud account ids, resource ids or em
  and en dashes in committed files.

### Audit
Imports, generations (requested and finished, with what was refused), test reviews, runs
(requested and finished: kind, tests, import, source label, commit, result, limit,
coverage, who triggered it and how), members, keys, providers, webhooks, settings and
sign-in failures write an `audit_log` row with actor, target, details, IP, organization
and project. A database trigger refuses `UPDATE` and `DELETE` on it; retention never
touches it.

### Infrastructure (AWS)
Private subnets for every task, the sandbox hosts, RDS and ElastiCache; TLS at the ALB
with WAF managed rules; RDS (TLS enforced), ElastiCache (TLS, AUTH), S3, Secrets Manager
and logs encrypted with the CMK; least-privilege task roles (the sandbox's and the web's
have none); IMDSv2 with a hop limit of 1 and blocked task metadata on the sandbox hosts;
`/metrics` answers 404 at the edge unless allowed; checkov in the gates.

## Reporting

Please report vulnerabilities privately as described in [SECURITY.md](../../SECURITY.md).

## Operator checklist

- Generate every secret randomly (at least 32 characters), keep them different, and set
  `ENVIRONMENT=production`, which refuses to start otherwise.
- Serve over HTTPS and set `COOKIE_SECURE=true`.
- Keep the sandbox exactly as shipped: its own network or security group reachable only
  from the worker, the sandbox seccomp profile, every capability dropped, read-only root,
  no privileged flag, `SANDBOX_CONCURRENCY=1`, and nothing but `SANDBOX_SECRET` in its
  environment.
- If anyone outside your organization can upload code, add a kernel boundary around the
  sandbox (gVisor, Kata, microVMs) or dedicated hosts, and keep the kernel patched.
- Rotate `SANDBOX_SECRET` after any suspected sandbox escape.
- Decide on model providers deliberately: with a hosted model, the analyzed source of the
  units being tested leaves your network. Use a local model (Ollama, an OpenAI-compatible
  server) where that matters.
- Give CI API keys only the scopes they need (`read` and `execute` to run accepted tests).
- Back up Postgres and the objects bucket; test a restore.
