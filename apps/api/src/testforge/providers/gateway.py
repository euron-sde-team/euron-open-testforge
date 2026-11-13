"""The door to model providers: an adapter built from sealed configuration and one model
call with retries.

Keys are opened only when a call is made and live only in the adapter object.
"""

from __future__ import annotations

import asyncio
import random

from testforge.core.container import Container
from testforge.providers import service
from testforge.providers.adapters import Adapter, adapter_for
from testforge.providers.models import ModelProvider
from testforge.providers.types import ModelRequest, ModelResponse, ProviderError


async def adapter(container: Container, row: ModelProvider) -> Adapter:
    if not row.enabled:
        raise ProviderError("The model provider is turned off", code="provider_disabled")
    return adapter_for(await service.config_of(container, row), container.http)


async def complete(
    adapter_: Adapter, request: ModelRequest, *, max_retries: int = 2
) -> ModelResponse:
    """One model call, retried on rate limits, overload and transport failures with
    exponential backoff and jitter (honouring ``Retry-After`` up to 30 s)."""
    attempt = 0
    while True:
        try:
            return await adapter_.complete(request, None)
        except ProviderError as exc:
            if not exc.retryable or attempt >= max_retries:
                raise
            delay = exc.retry_after_s if exc.retry_after_s is not None else min(2.0**attempt, 10.0)
            delay = min(delay, 30.0) * (0.75 + random.random() / 2)  # noqa: S311 jitter, not security
            attempt += 1
            await asyncio.sleep(delay)
