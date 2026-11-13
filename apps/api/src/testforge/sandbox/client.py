"""The worker's client for the sandbox service."""

from __future__ import annotations

import asyncio
import contextlib

import httpx

from testforge.sandbox.protocol import SIGNATURE_HEADER, RunRequest, RunResult, sign


class SandboxError(Exception):
    """The sandbox could not run the job (unreachable, busy, refused). ``retryable`` errors
    go back to the queue; the run itself is not counted as failed."""

    def __init__(self, message: str, *, retryable: bool, reason: str) -> None:
        super().__init__(message)
        self.message = message
        self.retryable = retryable
        self.reason = reason


class SandboxClient:
    def __init__(self, http: httpx.AsyncClient, base_url: str, secret: str) -> None:
        self.http = http
        self.base = base_url.rstrip("/")
        self.secret = secret

    def _headers(self, body: bytes) -> dict[str, str]:
        return {SIGNATURE_HEADER: sign(self.secret, body), "content-type": "application/json"}

    async def run(self, req: RunRequest) -> RunResult:
        """Run a suite and wait for it. Cancelling the awaiting task kills the run in the
        sandbox."""
        body = req.model_dump_json().encode()
        try:
            resp = await self.http.post(
                f"{self.base}/v1/runs",
                content=body,
                headers=self._headers(body),
                # The sandbox enforces the wall clock itself; this covers queueing for a
                # slot (30 s), building the workspace and reading the results.
                timeout=httpx.Timeout(req.limits.wall_s + 90, connect=5),
            )
        except asyncio.CancelledError:
            with contextlib.suppress(Exception):
                await asyncio.shield(self.kill(req.job_id))
            raise
        except httpx.HTTPError as exc:
            raise SandboxError(
                f"The sandbox service is unreachable ({exc.__class__.__name__})",
                retryable=True,
                reason="unreachable",
            ) from exc
        if resp.status_code == 429:
            raise SandboxError("The sandbox is busy", retryable=True, reason="busy")
        if resp.status_code >= 400:
            raise SandboxError(
                f"The sandbox refused the run (HTTP {resp.status_code}): {resp.text[:300]}",
                retryable=resp.status_code >= 500,
                reason="refused",
            )
        return RunResult.model_validate_json(resp.content)

    async def kill(self, job_id: str) -> None:
        await self.http.delete(
            f"{self.base}/v1/runs/{job_id}", headers=self._headers(b""), timeout=5
        )

    async def health(self) -> bool:
        try:
            resp = await self.http.get(f"{self.base}/healthz", timeout=5)
        except httpx.HTTPError:
            return False
        return resp.status_code == 200
