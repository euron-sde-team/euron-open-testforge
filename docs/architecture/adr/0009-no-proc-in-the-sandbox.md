# ADR-0009: No /proc inside the sandbox

- **Status:** Accepted
- **Date:** 2026-11-13

## Context

Docker overmounts parts of a container's `/proc` (`/proc/kcore`, `/proc/keys` and others).
The kernel refuses to mount a fresh procfs inside a user namespace when the existing one
has such overmounts, so nsjail cannot give a jail its own `/proc` without privileges.
Mounting the container's `/proc` instead would show the service's processes and
environment to the run.

## Decision

- Run every jail with `--disable_proc`: there is no `/proc` inside.
- pytest and coverage.py work without it. Node's `process.memoryUsage()` reads
  `/proc/self/statm` and throws, and Vitest calls it between test files and would wait
  forever. `sandbox/toolchain/js/no-proc.cjs`, loaded into every Node process through
  `NODE_OPTIONS=--require`, wraps it: the original result when it works; otherwise the
  peak resident size from `process.resourceUsage()` (getrusage) and the heap fields from
  `v8.getHeapStatistics()`.
- Vitest runs its test files in a single forked child process, so every Node process gets
  the shim (worker threads would not inherit `NODE_OPTIONS`).
- The service itself raises a run's `oom_score_adj` through its own `/proc` before
  `exec`-ing nsjail, which is outside the jail.

## Consequences

**Good**
- Nothing about other processes or the service's environment is visible to a run, and no
  privilege is needed.

**Bad / caveats**
- Any tool under test that requires `/proc` fails inside the sandbox; the sandbox suite
  checks that `/proc/self/environ` cannot be read.
- `process.memoryUsage().rss` reports the peak instead of the current resident size when
  `/proc` is missing.
