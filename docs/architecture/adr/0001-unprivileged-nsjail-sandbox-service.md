# ADR-0001: Execute tests in nsjail inside an unprivileged sandbox service

- **Status:** Accepted
- **Date:** 2026-11-13

## Context

TestForge's promise is that every execution, of a generated test or of an uploaded
project and its own suite, happens with no network, no credentials and fixed limits.
Running a project's tests executes the whole project: its imports, its fixtures, anything
a dependency does on import. Comparable tools run tests in the developer's own environment
(no isolation) or keep isolation in a paid tier.

The usual sandboxes for hostile code either trust Docker alone (a container per run: slow
to start, a weak boundary, and the runner needs the Docker socket) or run nsjail or
isolate inside a **privileged** container, because cgroup v2 needs privilege or
delegation. Judge0's 2024 advisories (CVE-2024-28185, CVE-2024-28189, CVE-2024-29021)
became host takeovers because an escape from the inner sandbox was root in a privileged
container. Euron Open CodeJudge solved this with nsjail built from user namespaces inside
an unprivileged container; TestForge reuses that design.

The open question was where the sandbox lives relative to the worker, which holds the
database URL, the model provider keys and GitHub tokens.

## Decision

- A separate process role and image, `testforge sandbox`: a small HTTP service whose only
  job is to run one test suite in a fresh nsjail and return measurements and the runner's
  files.
- The worker calls it with `POST /v1/runs`, the whole workspace inline, signed with
  HMAC-SHA256 over a timestamp and the body (`SANDBOX_SECRET`). The sandbox holds no other
  credential and needs no database, queue or storage.
- The container drops every capability, sets `no-new-privileges`, has a read-only root and
  Docker's default seccomp profile plus only `clone, unshare, mount, umount2, pivot_root,
  sethostname, setdomainname, setns` (`infra/docker/sandbox-seccomp.json`). Each run gets
  user, PID, network, mount, IPC and UTS namespaces, uid 65534, a kafel filter refusing
  namespace, mount, ptrace, bpf, keyring, perf and io_uring calls, read-only system
  directories and toolchain, and its own workspace.
- Its network reaches nothing: an internal Compose network shared with the worker only; on
  AWS a security group that admits the worker and has no egress.

## Consequences

**Good**
- An escape from a jail lands as an unprivileged user in a container with no capability,
  no credential but the signing secret, and no route anywhere.
- The worker never executes project code, so the credentials it needs are never next to
  untrusted code.
- A jail starts in milliseconds, not a container start; the same image runs in Compose and
  ECS with the same hardening; the hostile suite (`make test-sandbox`) proves it on every
  change.

**Bad / caveats**
- User namespaces are kernel attack surface; for open uploads add gVisor, Kata, microVMs or
  dedicated hosts ([sandbox.md](../sandbox.md)).
- The custom seccomp profile rules out Fargate: the sandbox runs on an EC2 capacity
  provider on AWS.
- Sending the workspace inline bounds its size (60 MB at the sandbox) and costs one copy
  per run.
- No cgroups: see [ADR-0002](0002-rlimits-not-cgroups.md).

## Alternatives considered

- **Run tests in the worker's container**: the worker holds every credential; one escape
  would expose them all.
- **A sandbox worker that pulls jobs from the queue** (CodeJudge's judges): it would need
  queue and storage access to fetch work and workspaces. Pushing a self-contained request
  lets the sandbox own nothing.
- **A container per run through the Docker socket**: handing the Docker socket to the
  service that runs untrusted code is a host takeover waiting to happen.
- **isolate in a privileged container**: exact cgroup accounting, but privileged.
- **gVisor or microVMs for every run**: a stronger boundary and a good addition, not
  available on Docker Desktop by default; documented as the hardening step.
