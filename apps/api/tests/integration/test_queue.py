"""The job queue without a running worker: claims, leases and the reaper."""

from __future__ import annotations

import asyncio

import pytest

from tests.integration.conftest import Stack, WorkerThread

pytestmark = pytest.mark.integration


@pytest.fixture
def run_worker() -> bool:
    return False


async def test_a_job_whose_worker_died_is_reclaimed(ready: Stack) -> None:
    """The lease reaper hands a job back when its worker stops (crash safety)."""
    shop = ready
    await shop.import_zip("python-shop", wait=0)
    # No worker runs: the import job is queued. Claim it as a worker that then dies.
    from testforge.core.container import Container
    from testforge.jobs import queue
    from testforge.jobs.tasks import reap_leases

    container = Container.build(shop.settings)
    try:
        async with container.db.sessionmaker() as session:
            job = await queue.claim(session, "dead-worker", 0.1)
        assert job is not None
        await asyncio.sleep(0.3)
        await reap_leases(container)
        async with container.db.sessionmaker() as session:
            depth = await queue.depth(session)
        assert depth["queued"] == 1
    finally:
        await container.close()
    shop.worker = WorkerThread(shop.settings).start()
    imports = await shop.ok("GET", shop.p("/imports"))
    imp = await shop.ok("GET", shop.p(f"/imports/{imports[0]['id']}"), params={"wait": 60})
    assert imp["status"] == "ready"
