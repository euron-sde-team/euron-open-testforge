"""Shared plumbing for provider adapters: HTTP errors and argument parsing. Each adapter
only translates its own wire format. TestForge waits for whole answers (a query is only
useful complete), so requests are never streamed."""

from __future__ import annotations

import abc
import json
from dataclasses import dataclass, field
from typing import Any

import httpx

from testforge.providers.types import (
    ModelRequest,
    ModelResponse,
    OnDelta,
    ProviderError,
    ToolCall,
    classify_status,
)


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    kind: str
    base_url: str
    api_key: str | None = None
    # Extra headers on every request (a gateway's tenant or budget headers).
    headers: dict[str, str] = field(default_factory=dict)
    timeout_s: float = 120.0


def parse_arguments(raw: str | dict[str, Any] | None) -> dict[str, Any] | None:
    """Tool call arguments as a dict, or None when they are not a JSON object."""
    if isinstance(raw, dict):
        return raw
    if raw is None or not str(raw).strip():
        return {}
    try:
        value = json.loads(raw)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _retry_after(resp: httpx.Response) -> float | None:
    raw = resp.headers.get("retry-after")
    if not raw:
        return None
    try:
        return max(float(raw), 0.0)
    except ValueError:
        return None


async def raise_for_status(resp: httpx.Response) -> None:
    if resp.status_code < 400:
        return
    body = (await resp.aread()).decode("utf-8", "replace")[:600]
    message = body
    try:
        parsed = json.loads(body)
        err = parsed.get("error", parsed) if isinstance(parsed, dict) else parsed
        if isinstance(err, dict):
            message = str(err.get("message") or err)
        elif isinstance(err, str):
            message = err
    except ValueError:
        pass
    retryable, code = classify_status(resp.status_code)
    raise ProviderError(
        f"The provider answered {resp.status_code}: {message}".strip(),
        status=resp.status_code,
        retryable=retryable,
        retry_after_s=_retry_after(resp),
        code=code,
    )


def transport_error(exc: Exception) -> ProviderError:
    if isinstance(exc, httpx.TimeoutException):
        return ProviderError(
            "The provider did not answer in time", retryable=True, code="provider_timeout"
        )
    return ProviderError(
        f"Could not reach the provider: {exc.__class__.__name__}",
        retryable=True,
        code="provider_unreachable",
    )


class Adapter(abc.ABC):
    """One provider family's wire format."""

    def __init__(self, config: ProviderConfig, http: httpx.AsyncClient) -> None:
        self.config = config
        self.http = http

    @property
    def base(self) -> str:
        return self.config.base_url.rstrip("/")

    @abc.abstractmethod
    async def complete(self, req: ModelRequest, on_delta: OnDelta | None = None) -> ModelResponse:
        """One model call. Cancelling the awaiting task aborts the HTTP request."""

    @abc.abstractmethod
    async def list_models(self) -> list[str]:
        """Model ids the provider offers this key."""

    async def _post(
        self, url: str, payload: dict[str, Any], headers: dict[str, str]
    ) -> dict[str, Any]:
        try:
            resp = await self.http.post(
                url,
                json=payload,
                headers={**self.config.headers, **headers},
                timeout=self.config.timeout_s,
            )
        except httpx.HTTPError as exc:
            raise transport_error(exc) from exc
        await raise_for_status(resp)
        try:
            body = resp.json()
        except ValueError as exc:
            raise ProviderError(
                "The provider answered with something that is not JSON", retryable=True
            ) from exc
        if not isinstance(body, dict):
            raise ProviderError("The provider answered with an unexpected shape")
        return body

    async def _get(self, url: str, headers: dict[str, str]) -> dict[str, Any]:
        try:
            resp = await self.http.get(
                url, headers={**self.config.headers, **headers}, timeout=self.config.timeout_s
            )
        except httpx.HTTPError as exc:
            raise transport_error(exc) from exc
        await raise_for_status(resp)
        body = resp.json()
        return body if isinstance(body, dict) else {"data": body}


def call(id_: str, name: str, raw: str | dict[str, Any] | None) -> ToolCall:
    text = raw if isinstance(raw, str) else json.dumps(raw or {})
    return ToolCall(id=id_, name=name, arguments=parse_arguments(raw), raw_arguments=text)
