"""Reports, webhooks, the overview, usage, system state, the queue under failure."""

from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
from typing import Any

import httpx
import pytest

from tests.integration.conftest import Stack

pytestmark = pytest.mark.integration


async def _a_failed_run(shop: Stack) -> dict[str, Any]:
    gen = await shop.generate(kinds=["unit"])
    await shop.accept_all(gen["id"])
    return await shop.run(kind="generated")


async def test_reports_in_csv_and_html(shop: Stack) -> None:
    run = await _a_failed_run(shop)
    html_report = await shop.ok(
        "POST",
        shop.p("/reports"),
        {"scope": "run", "run_id": run["id"], "format": "html"},
        status=201,
    )
    resp = await shop.client.get(shop.p(f"/reports/{html_report['id']}/download"))
    assert resp.status_code == 200
    assert "sandbox" in resp.headers["content-security-policy"]
    page = resp.text
    assert "Failures, explained" in page and "33.34" in page and "<script" not in page
    csv_report = await shop.ok(
        "POST", shop.p("/reports"), {"scope": "project", "format": "csv"}, status=201
    )
    data = (await shop.client.get(shop.p(f"/reports/{csv_report['id']}/download"))).text
    rows = list(csv.reader(io.StringIO(data)))
    assert rows[0][:4] == ["started", "run", "kind", "status"]
    assert rows[1][1] == run["id"]
    run_csv = await shop.ok(
        "POST",
        shop.p("/reports"),
        {"scope": "run", "run_id": run["id"], "format": "csv"},
        status=201,
    )
    cases = list(
        csv.DictReader(
            io.StringIO((await shop.client.get(shop.p(f"/reports/{run_csv['id']}/download"))).text)
        )
    )
    failed = [c for c in cases if c["outcome"] == "failed"]
    assert failed and failed[0]["expected"] == "[33.34, 33.33, 33.33]"
    listed = await shop.ok("GET", shop.p("/reports"))
    assert len(listed) == 3


async def test_outbound_webhook_is_signed_and_retried(shop: Stack) -> None:
    url = f"{shop.mock_ai_url}/_mock/hooks/ci"
    hook = await shop.ok(
        "POST",
        shop.p("/webhooks"),
        {"name": "CI", "url": url, "events": ["run.finished"]},
        status=201,
    )
    async with httpx.AsyncClient() as http:
        # The receiver is down for the first attempt: the delivery stays pending, then lands.
        await http.post(f"{shop.mock_ai_url}/_mock/fail", params={"status": 503, "times": 0})
    run = await shop.run(kind="project")
    from testforge.core.container import Container
    from testforge.webhooks import service as webhooks

    container = Container.build(shop.settings)
    try:
        assert await webhooks.deliver_due(container) == 1
    finally:
        await container.close()
    async with httpx.AsyncClient() as http:
        received = (await http.get(f"{shop.mock_ai_url}/_mock/hooks")).json()
    assert len(received) == 1
    body = received[0]["body"].encode()
    payload = json.loads(body)
    assert payload["run"]["id"] == run["id"] and payload["run"]["status"] == "passed"
    sig = dict(p.split("=", 1) for p in received[0]["headers"]["x-testforge-signature"].split(","))
    expected = hmac.new(
        hook["secret"].encode(), f"{sig['t']}.".encode() + body, hashlib.sha256
    ).hexdigest()
    assert hmac.compare_digest(sig["v1"], expected)
    deliveries = await shop.ok("GET", shop.p(f"/webhooks/{hook['id']}/deliveries"))
    assert deliveries[0]["status"] == "delivered" and deliveries[0]["attempts"] == 1


async def test_a_failing_receiver_is_retried_with_backoff(shop: Stack) -> None:
    hook = await shop.ok(
        "POST", shop.p("/webhooks"), {"name": "Down", "url": "http://127.0.0.1:9/hook"}, status=201
    )
    await shop.run(kind="project")
    from testforge.core.container import Container
    from testforge.webhooks import service as webhooks

    container = Container.build(shop.settings)
    try:
        await webhooks.deliver_due(container)
        # Not due again yet: backoff.
        assert await webhooks.deliver_due(container) == 0
    finally:
        await container.close()
    d = (await shop.ok("GET", shop.p(f"/webhooks/{hook['id']}/deliveries")))[0]
    assert d["status"] == "pending" and d["attempts"] == 1 and d["last_error"]


async def test_overview_usage_coverage_and_system(shop: Stack) -> None:
    await _a_failed_run(shop)
    ov = await shop.ok("GET", shop.p("/overview"))
    assert ov["current_import"]["languages"] == ["python"]
    assert ov["tests"]["accepted"] > 5
    assert ov["rejected_tests"] >= 1
    assert ov["runs_by_status"] == {"failed": 1}
    assert ov["pass_rate"] == 0.0
    assert ov["coverage_percent"] is not None and ov["coverage_trend"]
    usage = await shop.ok("GET", shop.p("/usage"))
    assert usage["totals"]["generations"] == 1 and usage["totals"]["runs"] == 1
    assert usage["totals"]["sandbox_ms"] > 0
    assert usage["by_model"][0]["model"] == "testforge-mock"
    system = await shop.ok("GET", "/api/v1/system")
    assert system["sandbox"] is True and system["runs"] == 1
    assert (await shop.client.get("/readyz")).status_code == 200
    metrics = (await shop.client.get("/metrics")).text
    assert "testforge_" in metrics


async def test_sandbox_down_fails_the_run_with_a_reason(stack: Stack) -> None:
    stack.settings.sandbox_url = "http://127.0.0.1:9"
    stack.settings.max_attempts = 1
    await stack.project()
    await stack.provider()
    await stack.import_zip("python-shop")
    run = await stack.run(kind="project", wait=60)
    assert run["status"] == "error", run
    assert "unreachable" in run["message"]
