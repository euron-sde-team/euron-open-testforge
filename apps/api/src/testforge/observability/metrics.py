"""Prometheus metrics. The API, the worker and the sandbox service each expose their own
registry."""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

JOBS = Counter(
    "testforge_jobs_total", "Background jobs that reached a final state", ["kind", "status"]
)
JOB_SECONDS = Histogram(
    "testforge_job_seconds",
    "Job duration from claim to final state, by kind",
    ["kind"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300, 900),
)
QUEUE_DEPTH = Gauge("testforge_queue_depth", "Jobs by state", ["status"])
ANALYSIS_SECONDS = Histogram(
    "testforge_analysis_seconds",
    "Static source analysis of one import (no execution)",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60),
)
GENERATED_TESTS = Counter(
    "testforge_generated_tests_total",
    "Generated tests by outcome of the assertion check (accepted or rejected, with the reason)",
    ["outcome"],
)
RUNS = Counter("testforge_runs_total", "Test runs that reached a final state", ["status"])
LIMITS_CROSSED = Counter(
    "testforge_sandbox_limits_total", "Runs stopped at a sandbox limit, by limit", ["limit"]
)
SANDBOX_SECONDS = Histogram(
    "testforge_sandbox_seconds",
    "Wall time of one sandboxed execution as the worker sees it (queueing in the sandbox included)",
    buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60, 120, 300, 900),
)
SANDBOX_FAILURES = Counter(
    "testforge_sandbox_failures_total",
    "Sandbox executions that failed for a reason other than the tests "
    "(unreachable, busy, refused, launch)",
    ["reason"],
)
MODEL_CALLS = Counter("testforge_model_calls_total", "Model calls", ["kind", "outcome"])
MODEL_LATENCY = Histogram(
    "testforge_model_latency_seconds",
    "Model call latency",
    ["kind"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 4, 8, 16, 32, 64, 128),
)
TOKENS = Counter("testforge_tokens_total", "Model tokens", ["direction"])
WEBHOOK_DELIVERIES = Counter(
    "testforge_webhook_deliveries_total", "Outbound webhook delivery attempts", ["outcome"]
)
DEPENDENCY_ERRORS = Counter(
    "testforge_dependency_errors_total",
    "Failed calls to a dependency",
    ["dependency", "operation"],
)
