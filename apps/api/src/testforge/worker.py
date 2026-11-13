"""The worker and the scheduler.

``testforge worker`` handles queued jobs (``jobs/handlers.py``): imports (download, unpack,
static analysis), generations (prompt, model call, assertion check) and runs (the sandbox
service). Stateless and safe to run as many replicas: jobs are claimed with ``FOR UPDATE
SKIP LOCKED`` and leased (``jobs/queue.py``), and the lease is renewed while a long sandbox
run is in progress. Up to ``WORKER_CONCURRENCY`` jobs run at once as asyncio tasks. Idle
workers wake on a queue notification or poll. SIGTERM stops claiming and waits for running
jobs up to the grace period; their leases make a hard kill safe (another worker takes them).

``testforge scheduler`` runs the periodic tasks: the lease reaper, webhook deliveries,
retention and queue gauges. Prometheus metrics on ``WORKER_METRICS_PORT``.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import socket
import time

from prometheus_client import start_http_server

from testforge.core.config import Settings, get_settings
from testforge.core.container import Container
from testforge.core.db import import_all_models
from testforge.core.logs import configure_logging
from testforge.core.tasks import tasks
from testforge.jobs import queue
from testforge.jobs.handlers import RetryLaterError, handle, mark_failed
from testforge.jobs.models import Job
from testforge.observability import metrics

log = logging.getLogger("testforge.worker")
SHUTDOWN_GRACE_S = 25.0


def import_task_modules() -> None:
    """Every module that registers a periodic task."""
    from testforge.jobs import tasks as _jobs  # noqa: F401


async def process(container: Container, job: Job, owner: str, settings: Settings) -> None:
    """Handle one claimed job: renew its lease while it runs, then finish it under the
    lease (or put it back, or fail it)."""
    started = time.monotonic()
    stop = asyncio.Event()

    async def keep_lease() -> None:
        while not stop.is_set():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=settings.lease_s / 3)
            if stop.is_set():
                return
            try:
                async with container.db.sessionmaker() as s:
                    await queue.renew(s, job.id, owner, settings.lease_s)
            except Exception:
                log.warning("lease renewal failed", extra={"job": str(job.id)})

    renewer = asyncio.create_task(keep_lease())
    status, error = "done", None
    try:
        async with container.db.sessionmaker() as session:
            await handle(container, session, job)
    except RetryLaterError as r:
        stop.set()
        if not r.count or job.attempts < settings.max_attempts:
            async with container.db.sessionmaker() as session:
                await queue.retry_later(session, job.id, owner, r.delay_s, count=r.count)
            log.info("job put back", extra={"job": str(job.id), "reason": r.reason})
            return
        status, error = "failed", r.reason
        await mark_failed(
            container, job, f"{r.reason}. Try again, and tell an admin if it keeps happening"
        )
    except Exception as exc:
        log.exception("job failed", extra={"job": str(job.id), "kind": job.kind})
        if job.attempts < settings.max_attempts:
            stop.set()
            async with container.db.sessionmaker() as session:
                await queue.retry_later(
                    session, job.id, owner, min(2**job.attempts, 30), count=True
                )
            return
        status, error = "failed", f"{exc.__class__.__name__}: {exc}"[:2000]
        await mark_failed(
            container, job, "TestForge hit an internal error handling this. Try again"
        )
    finally:
        stop.set()
        renewer.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await renewer
    async with container.db.sessionmaker() as session:
        await queue.finish(session, job.id, owner, status, error)
        await session.commit()
    metrics.JOBS.labels(job.kind, status).inc()
    metrics.JOB_SECONDS.labels(job.kind).observe(time.monotonic() - started)
    await container.pubsub.publish(queue.job_channel(job.ref_id), status)


def worker_name() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


async def tick(container: Container) -> bool:
    busy = False
    for name, task in tasks().items():
        try:
            handled = await task(container)
        except Exception:
            log.exception("task %s failed", name)
            continue
        if handled:
            log.info("task done", extra={"task": name, "items": handled})
            busy = True
    return busy


async def periodic_loop(
    container: Container, stop: asyncio.Event, settings: Settings, wake: asyncio.Event | None
) -> None:
    while not stop.is_set():
        started = time.monotonic()
        busy = await tick(container)
        if busy and wake is not None:
            wake.set()
        delay = 0.5 if busy else max(settings.task_interval_s - (time.monotonic() - started), 0.5)
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=delay)


async def serve(
    container: Container, stop: asyncio.Event, settings: Settings, *, run_tasks: bool = False
) -> None:
    name = worker_name()
    wake = asyncio.Event()
    slots = asyncio.Semaphore(settings.worker_concurrency)
    running: set[asyncio.Task[None]] = set()

    async def listen() -> None:
        while not stop.is_set():
            try:
                async with container.pubsub.listen(queue.QUEUE_CHANNEL) as sub:
                    while not stop.is_set():
                        if await sub.get(1.0):
                            wake.set()
            except Exception:
                await asyncio.sleep(2)

    async def one(slot_name: str) -> bool:
        async with container.db.sessionmaker() as session:
            job = await queue.claim(session, slot_name, settings.lease_s)
        if job is None:
            return False

        async def go() -> None:
            try:
                await process(container, job, slot_name, settings)
            finally:
                slots.release()

        task = asyncio.create_task(go())
        running.add(task)
        task.add_done_callback(running.discard)
        return True

    async def until(event: asyncio.Event, wait_s: float | None = None) -> None:
        """Wait for ``event`` or ``stop``, whichever comes first (never cancelled mid-query)."""
        waits = [asyncio.ensure_future(event.wait()), asyncio.ensure_future(stop.wait())]
        try:
            await asyncio.wait(waits, timeout=wait_s, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for w in waits:
                w.cancel()

    async def claimer() -> None:
        n = 0
        while not stop.is_set():
            acquired = asyncio.ensure_future(slots.acquire())
            stopping = asyncio.ensure_future(stop.wait())
            await asyncio.wait([acquired, stopping], return_when=asyncio.FIRST_COMPLETED)
            stopping.cancel()
            if not acquired.done() or stop.is_set():
                acquired.cancel()
                if acquired.done() and not acquired.cancelled():
                    slots.release()
                return
            n += 1
            try:
                claimed = await one(f"{name}#{n}")
            except Exception:
                log.exception("claim failed")
                claimed = False
            if not claimed:
                slots.release()
                await until(wake, settings.worker_poll_interval_s)
                wake.clear()

    listener = asyncio.create_task(listen())
    # The claimer and the periodic tasks finish their current (short) transaction and stop
    # on their own; cancelling them mid-query could strand a connection in a transaction.
    graceful = [asyncio.create_task(claimer())]
    if run_tasks:
        graceful.append(asyncio.create_task(periodic_loop(container, stop, settings, wake)))
    await stop.wait()
    log.info("stopping: %d running jobs get %ss to finish", len(running), SHUTDOWN_GRACE_S)
    listener.cancel()
    await asyncio.wait(graceful, timeout=SHUTDOWN_GRACE_S)
    if running:
        _, pending = await asyncio.wait(running, timeout=SHUTDOWN_GRACE_S)
        for t in pending:
            t.cancel()
        await asyncio.gather(*pending, return_exceptions=True)


async def _main(role: str) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    import_all_models()
    import_task_modules()
    if settings.worker_metrics_port:
        start_http_server(settings.worker_metrics_port)
    container = Container.build(settings)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    log.info("%s started", role, extra={"concurrency": settings.worker_concurrency})
    try:
        if role == "scheduler":
            await periodic_loop(container, stop, settings, None)
        else:
            await serve(container, stop, settings)
    finally:
        await container.close()
        log.info("%s stopped", role)


async def main() -> None:
    await _main("worker")


async def scheduler_main() -> None:
    await _main("scheduler")
