"""Tenancy (A11), roles, API key scopes, and the append-only audit log (A10)."""

from __future__ import annotations

import httpx
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from tests.integration.conftest import CSRF, Stack, login

pytestmark = pytest.mark.integration


async def _rival(stack: Stack) -> tuple[httpx.AsyncClient, str]:
    """A second organization with its own owner and project."""
    email, password = "rival@example.test", "Rival-Pass-123"
    await stack.ok("PATCH", "/api/v1/instance/settings", {"allow_signup": True})
    resp = await stack.client.post(
        "/api/v1/auth/signup",
        json={"email": email, "name": "Rival", "password": password, "organization": "Rival Inc"},
    )
    assert resp.status_code == 201, resp.text
    rival = await login(stack.api_url, {"email": email, "password": password})
    org = (await rival.get("/api/v1/orgs")).json()[0]
    proj = (
        await rival.post("/api/v1/projects", json={"org_id": org["id"], "name": "Theirs"})
    ).json()
    return rival, proj["id"]


async def test_another_organization_gets_404_for_everything_of_ours(shop: Stack) -> None:
    """A11: projects, generated tests, run history and everything else."""
    gen = await shop.generate(kinds=["unit"])
    tests = await shop.accept_all(gen["id"])
    run = await shop.run(kind="generated")
    imp = (await shop.ok("GET", shop.p("/imports")))[0]
    rival, theirs = await _rival(shop)
    try:
        ours = shop.project_id
        for path in (
            "",
            "/imports",
            f"/imports/{imp['id']}",
            f"/imports/{imp['id']}/units",
            f"/imports/{imp['id']}/files",
            "/analysis",
            "/tests",
            f"/tests/{tests[0]['id']}",
            "/generations",
            f"/generations/{gen['id']}",
            "/runs",
            f"/runs/{run['id']}",
            f"/runs/{run['id']}/coverage",
            f"/runs/{run['id']}/failures",
            "/coverage",
            "/overview",
            "/audit-logs",
            "/providers",
            "/usage",
            "/pulls",
            "/specs",
            "/reports",
            "/webhooks",
        ):
            resp = await rival.get(f"/api/v1/projects/{ours}{path}")
            assert resp.status_code == 404, (path, resp.status_code)
        for method, path, body in (
            ("POST", "/runs", {"kind": "generated"}),
            ("POST", "/tests/generate", {"kinds": ["unit"]}),
            ("PATCH", f"/tests/{tests[0]['id']}", {"status": "discarded"}),
        ):
            resp = await rival.request(method, f"/api/v1/projects/{ours}{path}", json=body)
            assert resp.status_code == 404, (path, resp.status_code)
        # Inside their own project, our ids do not exist either.
        base = f"/api/v1/projects/{theirs}"
        for path in (f"/tests/{tests[0]['id']}", f"/runs/{run['id']}", f"/imports/{imp['id']}"):
            assert (await rival.get(base + path)).status_code == 404, path
        resp = await rival.post(
            base + "/runs", json={"kind": "generated", "test_ids": [tests[0]["id"]]}
        )
        assert resp.status_code in (400, 404)
        assert (await rival.get(f"/api/v1/orgs/{shop.org_id}/audit-logs")).status_code == 404
    finally:
        await rival.aclose()


async def test_every_run_is_in_the_append_only_audit_log(shop: Stack) -> None:
    """A10: what ran, from which source, the result, and who triggered it, per project."""
    gen = await shop.generate(kinds=["unit"])
    tests = await shop.accept_all(gen["id"])
    run = await shop.run(kind="generated")
    entries = await shop.audit(target_id=run["id"])
    actions = {e["action"]: e for e in entries}
    assert set(actions) == {"run.requested", "run.finished"}
    finished = actions["run.finished"]["details"]
    assert finished["status"] == run["status"]
    assert finished["passed"] == run["passed"]
    assert finished["failed"] == run["failed"]
    assert set(finished["tests"]) == {t["id"] for t in tests}
    assert finished["import_id"] == run["import_id"]
    assert finished["triggered_by"] == "admin@example.test"
    assert actions["run.requested"]["actor_email"] == "admin@example.test"
    all_actions = {e["action"] for e in await shop.audit()}
    assert {
        "import.created",
        "import.ready",
        "generation.requested",
        "generation.finished",
        "test.accepted",
    } <= all_actions
    gen_entry = next(e for e in await shop.audit(action="generation.finished"))
    assert set(gen_entry["details"]["tests"]) >= {t["id"] for t in tests}
    # A viewer reads the project's trail too.
    viewer, _ = await shop.member("viewer")
    resp = await viewer.get(shop.p("/audit-logs"))
    assert resp.status_code == 200 and resp.json()["items"]
    await viewer.aclose()
    # The database itself refuses to change history.
    engine = create_async_engine(shop.settings.database_url)
    try:
        async with engine.begin() as conn:
            with pytest.raises(sa.exc.DBAPIError, match="append-only"):
                await conn.execute(sa.text("UPDATE audit_log SET action = 'x'"))
        async with engine.begin() as conn:
            with pytest.raises(sa.exc.DBAPIError, match="append-only"):
                await conn.execute(sa.text("DELETE FROM audit_log"))
    finally:
        await engine.dispose()


async def test_viewers_read_but_cannot_generate_or_run(shop: Stack) -> None:
    viewer, _ = await shop.member("viewer")
    try:
        assert (await viewer.get(shop.p("/tests"))).status_code == 200
        assert (await viewer.get(shop.p("/runs"))).status_code == 200
        for path, body in (
            ("/tests/generate", {"kinds": ["unit"]}),
            ("/runs", {"kind": "project"}),
            ("/imports/github", {"repo": "euron-demo/python-shop"}),
            ("/specs", {"document": '{"openapi": "3.0.0", "paths": {"/a": {}}}'}),
        ):
            resp = await viewer.post(shop.p(path), json=body)
            assert resp.status_code == 403, (path, resp.text)
            assert resp.json()["error"]["code"] == "insufficient_role"
        editor, _ = await shop.member("editor")
        gen = await shop.generate(kinds=["unit"], client=editor)
        assert gen["status"] == "done"
        resp = await editor.post(shop.p("/providers"), json={"name": "x", "kind": "mock"})
        assert resp.status_code == 403
        await editor.aclose()
    finally:
        await viewer.aclose()


async def test_api_key_scopes(shop: Stack) -> None:
    key = await shop.ok(
        "POST", shop.p("/api-keys"), {"name": "ci", "scopes": ["read", "execute"]}, status=201
    )
    assert key["key"].startswith("tfk_")
    async with httpx.AsyncClient(
        base_url=shop.api_url, headers={"authorization": f"Bearer {key['key']}"}, timeout=180
    ) as ci:
        current = (await ci.get("/api/v1/projects/current")).json()
        assert current["id"] == shop.project_id
        run = await ci.post(shop.p("/runs"), params={"wait": 120}, json={"kind": "project"})
        assert run.status_code == 202, run.text
        assert run.json()["trigger"] == "api"
        denied = await ci.post(shop.p("/tests/generate"), json={"kinds": ["unit"]})
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "insufficient_scope"
    await shop.ok("DELETE", shop.p(f"/api-keys/{key['id']}"))
    async with httpx.AsyncClient(base_url=shop.api_url, headers={"x-api-key": key["key"]}) as ci:
        assert (await ci.get(shop.p("/runs"))).status_code == 401


async def test_cookie_sessions_need_the_csrf_header(shop: Stack) -> None:
    async with httpx.AsyncClient(base_url=shop.api_url) as browser:
        resp = await browser.post(
            "/api/v1/auth/login", json={"email": "admin@example.test", "password": "Admin-Pass-123"}
        )
        assert resp.status_code == 200
        no_header = await browser.post(shop.p("/runs"), json={"kind": "project"})
        assert no_header.status_code == 403
        assert no_header.json()["error"]["code"] == "csrf_required"
        with_header = await browser.post(shop.p("/runs"), json={"kind": "project"}, headers=CSRF)
        assert with_header.status_code == 202
