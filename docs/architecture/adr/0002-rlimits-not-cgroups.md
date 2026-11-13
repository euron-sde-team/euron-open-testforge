# ADR-0002: Limits from rlimits and one run per sandbox process, not cgroups

- **Status:** Accepted
- **Date:** 2026-11-13

## Context

A run must stop at its CPU, memory, output and wall clock budget and say which one it
crossed. cgroups give exact memory ceilings and process counts, but creating them needs a
privileged or cgroup-delegated container, which [ADR-0001](0001-unprivileged-nsjail-sandbox-service.md)
rules out. rlimits need no privilege but have gaps: `RLIMIT_NPROC` counts processes per
real uid, and every jail maps to the same outside uid (the service's); `RLIMIT_AS` limits
address space, not resident memory, which breaks V8, which reserves far more than it uses.

## Decision

- CPU (`RLIMIT_CPU`, the budget plus one second), address space for pytest (the budget
  plus 128 MB of interpreter overhead), processes per runner, file size (output), open
  files, stack and core dumps from rlimits; the wall clock from nsjail's `--time_limit`, with
  a backstop timer in the service.
- For Vitest (`memory_mode: rss`), cap the heap with `--max-old-space-size` and check peak
  resident memory after the run; raise the run's `oom_score_adj` to 1000 so the kernel
  kills the run, not the service.
- **One run at a time per sandbox process** (`SANDBOX_CONCURRENCY=1`), so the per-uid
  process count belongs to one run; scale with more sandbox replicas.
- Bound everything with the container's memory, CPU and pids limits.
- Decide which limit was crossed from measurements (`wait4` CPU time and peak memory,
  output sizes, signals, nsjail's log, out-of-memory markers) in a fixed order: output,
  wall clock, CPU, memory, processes.

## Consequences

**Good**
- No privilege needed; the same approach CodeJudge and DMOJ use.
- CPU time and peak memory from `wait4` are exact for the whole run.
- The limit a developer sees is a fact, not a guess, and the tests that finished before it
  are still reported.

**Bad / caveats**
- A Node run can briefly exceed its memory limit before the check (bounded by the
  container limit).
- Parallel runs need parallel sandbox processes; throughput per host is the number of
  sandbox tasks on it.
- The process limit includes the service's own threads, so it is set with headroom (128
  for pytest, 512 for Vitest).
