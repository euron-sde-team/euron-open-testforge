# ADR-0005: A PostgreSQL job queue with leases

- **Status:** Accepted
- **Date:** 2026-11-13

## Context

Imports, generations and runs are slow (downloads, model calls, sandbox runs of minutes)
and must survive a worker crash, a deploy, or a sandbox that is busy. The brief suggested
Celery with Redis. Every job is about a row that already lives in Postgres (an import, a
generation, a run), and Redis in TestForge is optional and runs with `allkeys-lru`.

## Decision

A `jobs` table in Postgres:

- **Enqueue** in the same transaction as the record, so a job exists exactly when its
  record does.
- **Claim** with one `UPDATE ... WHERE id = (SELECT ... FOR UPDATE SKIP LOCKED) RETURNING`,
  setting a lease owner and expiry and counting the attempt; partial indexes on queued and
  running rows keep it cheap.
- **Renew** the lease every third of `LEASE_S` while the job runs.
- **Finish** with a compare-and-set on `lease_owner`, so a worker that lost its lease
  cannot overwrite the new owner's work.
- **Reap** expired leases from the scheduler: back to the queue with backoff, or failed
  after `MAX_ATTEMPTS` with a message on the record.
- **Put back** without counting the attempt when the sandbox is busy.
- **Wake** idle workers and waiting API requests through pub/sub (Redis or in process),
  with polling as the fallback, so a lost message costs one poll interval.

## Consequences

**Good**
- One durable store; Redis can lose everything without losing work.
- Transactional enqueue: no job without its record, no record without its job.
- Inspectable with SQL; the queue depth is a query (`/api/v1/system`, the `job queue` log
  line, the CloudWatch alarm).

**Bad / caveats**
- Throughput is bounded by Postgres; at TestForge's job sizes (seconds to minutes each)
  that is far from the limit.
- No priorities or per-project fairness beyond `available_at` order in 0.1.0.

## Alternatives considered

- **Celery with Redis**: another moving part, and jobs would live in a store that can
  evict them.
- **Redis Streams with consumer groups** (CodeJudge's queue): good for many short jobs;
  needs Redis as durable storage with `noeviction`.
- **SQS**: fine on AWS, but one more emulated service locally and a second source of truth
  next to the record's own status.
