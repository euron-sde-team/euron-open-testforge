"""Publish and subscribe, for queue wake-ups and finished jobs.

Postgres holds every durable state; pub/sub only says "look again": a new job is queued
(workers wake), or a job finished (an API request waiting for it returns).
With Redis, messages cross processes (the worker publishes, the API listens). Without
Redis (one process in development), an in-process fan-out is used, and waiting falls back
to polling the database.

A subscription is read with ``get(wait_s)``, which returns None when nothing arrived in
time. Waiting can be abandoned at any moment without losing the subscription (unlike an
async generator, which a cancelled ``anext`` closes for good).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Protocol

from redis.asyncio import Redis
from redis.asyncio.client import PubSub as RedisSub


class Subscription(Protocol):
    async def get(self, wait_s: float) -> str | None: ...


class PubSub(Protocol):
    cross_process: bool

    async def publish(self, channel: str, message: str) -> None: ...
    def listen(self, channel: str) -> contextlib.AbstractAsyncContextManager[Subscription]: ...
    async def close(self) -> None: ...


class _RedisSubscription:
    def __init__(self, ps: RedisSub) -> None:
        self.ps = ps

    async def get(self, wait_s: float) -> str | None:
        msg = await self.ps.get_message(ignore_subscribe_messages=True, timeout=max(wait_s, 0.0))
        if msg is None:
            return None
        data = msg.get("data")
        return data.decode() if isinstance(data, bytes) else str(data)


class RedisPubSub:
    cross_process = True

    def __init__(self, url: str) -> None:
        self.redis: Redis = Redis.from_url(
            url, socket_timeout=10, socket_connect_timeout=5, health_check_interval=30
        )

    async def publish(self, channel: str, message: str) -> None:
        with contextlib.suppress(Exception):  # a lost wake-up only delays a poll
            await self.redis.publish(channel, message)

    @contextlib.asynccontextmanager
    async def listen(self, channel: str) -> AsyncIterator[Subscription]:
        ps = self.redis.pubsub(ignore_subscribe_messages=True)
        await ps.subscribe(channel)
        try:
            yield _RedisSubscription(ps)
        finally:
            with contextlib.suppress(Exception):
                await ps.unsubscribe(channel)
                await ps.aclose()  # type: ignore[no-untyped-call]

    async def close(self) -> None:
        await self.redis.aclose()


class _QueueSubscription:
    def __init__(self, q: asyncio.Queue[str]) -> None:
        self.q = q

    async def get(self, wait_s: float) -> str | None:
        try:
            return await asyncio.wait_for(self.q.get(), timeout=max(wait_s, 0.0))
        except TimeoutError:
            return None


class MemoryPubSub:
    cross_process = False

    def __init__(self) -> None:
        self._subs: dict[str, set[asyncio.Queue[str]]] = defaultdict(set)

    async def publish(self, channel: str, message: str) -> None:
        for q in list(self._subs.get(channel, ())):
            if q.qsize() < 1000:
                q.put_nowait(message)

    @contextlib.asynccontextmanager
    async def listen(self, channel: str) -> AsyncIterator[Subscription]:
        q: asyncio.Queue[str] = asyncio.Queue()
        self._subs[channel].add(q)
        try:
            yield _QueueSubscription(q)
        finally:
            self._subs[channel].discard(q)

    async def close(self) -> None:
        self._subs.clear()


def create_pubsub(redis_url: str) -> PubSub:
    return RedisPubSub(redis_url) if redis_url else MemoryPubSub()
