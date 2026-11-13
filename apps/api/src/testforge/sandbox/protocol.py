"""What the worker sends the sandbox service and what comes back, plus request signing.

Requests carry ``X-TF-Sandbox: t=<unix>,v1=<hmac-sha256(secret, "<t>.<body>")>``; the
sandbox refuses unsigned, wrongly signed or stale (older than 5 minutes) requests, so only
the worker, which holds SANDBOX_SECRET, can start a run.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Literal

from pydantic import BaseModel, Field, field_validator

SIGNATURE_HEADER = "x-tf-sandbox"
MAX_SKEW_S = 300

Limit = Literal["cpu", "memory", "wall_clock", "output", "processes"]


class WorkspaceFile(BaseModel):
    path: str = Field(min_length=1, max_length=400)
    content_b64: str

    @field_validator("path")
    @classmethod
    def _relative(cls, v: str) -> str:
        """Relative, no "..", no backslash or NUL. The server checks again on disk."""
        parts = v.split("/")
        if v.startswith("/") or "\x00" in v or "\\" in v or ".." in parts or "" in parts:
            raise ValueError("a workspace path must be relative and stay inside the workspace")
        return v


class SandboxLimits(BaseModel):
    cpu_s: int = Field(60, ge=1, le=7200)
    wall_s: int = Field(120, ge=1, le=7200)
    memory_mb: int = Field(1024, ge=64, le=65536)
    output_bytes: int = Field(4_000_000, ge=10_000, le=500_000_000)


class RunRequest(BaseModel):
    job_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    runner: Literal["pytest", "vitest"]
    files: list[WorkspaceFile] = Field(max_length=10_000)
    # Test files or directories to run, relative to the workspace; empty: discover.
    targets: list[str] = Field(default_factory=list, max_length=2_000)
    coverage: bool = True
    limits: SandboxLimits = Field(default_factory=SandboxLimits)


class RunResult(BaseModel):
    exit_code: int | None
    signal: int | None = None
    cpu_ms: int = 0
    wall_ms: int = 0
    memory_kb: int = 0
    output_bytes: int = 0
    # Which limit stopped the run (or was crossed during it), if any.
    limit_exceeded: Limit | None = None
    limit_detail: str = ""
    stdout_tail: str = ""
    stderr_tail: str = ""
    # The runner plugin's own files, verbatim: the final report (absent when the run was
    # stopped before it ended), the per-event log and the coverage tool's JSON report.
    report: str | None = None
    events: str = ""
    coverage: str | None = None
    coverage_tool: str = ""
    # The sandbox itself failed (nsjail could not start, a bad workspace): not the tests.
    error: str | None = None


def sign(secret: str, body: bytes, now: int | None = None) -> str:
    ts = int(now if now is not None else time.time())
    mac = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={ts},v1={mac}"


def verify(secret: str, body: bytes, header: str | None, now: float | None = None) -> bool:
    if not header:
        return False
    parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
    try:
        ts = int(parts.get("t", ""))
    except ValueError:
        return False
    if abs((now if now is not None else time.time()) - ts) > MAX_SKEW_S:
        return False
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, parts.get("v1", ""))
