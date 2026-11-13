# ADR-0008: One Python package for every role, two images

- **Status:** Accepted
- **Date:** 2026-11-13

## Context

TestForge has five process roles: the API, the worker, the scheduler, the sandbox service
and one-off commands (migrate, create-admin, seed-demo). The sandbox needs nsjail, a
Python test toolchain and a Node toolchain; the others need none of that. The sandbox and
the worker must agree exactly on the run protocol, the runner registry and the signing
scheme.

## Decision

- One package, `testforge`, with one CLI: `serve`, `worker`, `scheduler`, `sandbox`,
  `migrate`, `revision`, `create-admin`, `seed-demo`, `openapi`. The protocol
  (`sandbox/protocol.py`) and the runner registry (`sandbox/runners.yaml`) are imported by
  both sides from the same source.
- Two images: `infra/docker/server.Dockerfile` (api, worker, scheduler, migrate, CLI and
  the mock services) and `infra/docker/sandbox.Dockerfile` (the same package plus nsjail
  built from a pinned release, the toolchain under `/opt/toolchain`, and a `sandbox-test`
  target for the hostile suite). The service's own virtualenv (`/opt/venv`) is never
  mounted into a jail.

## Consequences

**Good**
- The worker and the sandbox cannot drift apart: a runner the API offers is one the
  sandbox runs, and a protocol change is one commit.
- The server image stays small and holds no toolchain or nsjail; the sandbox image holds no
  credential.

**Bad / caveats**
- The sandbox image carries the whole package, including code it never runs; that code is
  outside every jail.
- The sandbox image is the slow one to build (nsjail from source, the toolchains); see
  `TESTFORGE_APT_MIRROR` in [troubleshooting](../../guides/troubleshooting.md).
