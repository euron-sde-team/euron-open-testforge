"""Administration: instance users, organizations and their members, member notices, model
providers, project settings, sign-in and the request guards."""

from __future__ import annotations

import httpx
import pytest

from testforge.core import mail
from tests.integration.conftest import CSRF, Stack, login

pytestmark = pytest.mark.integration


async def test_instance_admins_manage_users(stack: Stack) -> None:
    created = await stack.ok(
        "POST",
        "/api/v1/users",
        {"email": "ops@example.test", "name": "Ops", "password": "Ops-Pass-1234"},
        status=201,
    )
    assert created["role"] == "user"
    resp = await stack.client.post(
        "/api/v1/users",
        json={"email": "ops@example.test", "name": "Again", "password": "Ops-Pass-1234"},
    )
    assert resp.status_code == 409
    weak = await stack.client.post(
        "/api/v1/users", json={"email": "w@example.test", "name": "W", "password": "alllowercase"}
    )
    assert weak.status_code in (400, 422)
    ops = await login(stack.api_url, {"email": "ops@example.test", "password": "Ops-Pass-1234"})
    try:
        denied = await ops.post(
            "/api/v1/users",
            json={"email": "x@example.test", "name": "x", "password": "Xx-Pass-12345"},
        )
        assert denied.status_code == 403
        promoted = await stack.ok(
            "PATCH", f"/api/v1/users/{created['id']}", {"role": "admin", "name": "Ops Lead"}
        )
        assert promoted["role"] == "admin" and promoted["name"] == "Ops Lead"
        await stack.ok("PATCH", f"/api/v1/users/{created['id']}", {"disabled": True})
        assert (await ops.get("/api/v1/auth/me")).status_code == 401
    finally:
        await ops.aclose()
    me = (await stack.client.get("/api/v1/auth/me")).json()
    resp = await stack.client.patch(f"/api/v1/users/{me['id']}", json={"disabled": True})
    assert resp.status_code in (400, 403, 409)
    users = await stack.ok("GET", "/api/v1/users")
    assert {u["email"] for u in users} >= {"admin@example.test", "ops@example.test"}
    settings = await stack.ok("GET", "/api/v1/instance/settings")
    changed = await stack.ok("PATCH", "/api/v1/instance/settings", {"site_name": "Test lab"})
    assert changed["site_name"] == "Test lab" and settings["allow_signup"] is False
    public = (await httpx.AsyncClient(base_url=stack.api_url).get("/api/v1/instance/public")).json()
    assert public["site_name"] == "Test lab"


async def test_organizations_and_their_members(stack: Stack) -> None:
    orgs = await stack.ok("GET", "/api/v1/orgs")
    assert [o["role"] for o in orgs] == ["owner"]
    second = await stack.ok("POST", "/api/v1/orgs", {"name": "Second Org"}, status=201)
    renamed = await stack.ok("PATCH", f"/api/v1/orgs/{second['id']}", {"name": "Second"})
    assert renamed["name"] == "Second"
    added = await stack.ok(
        "POST",
        f"/api/v1/orgs/{second['id']}/members",
        {
            "email": "lead@example.test",
            "role": "admin",
            "name": "Lead",
            "password": "Lead-Pass-123",
        },
        status=201,
    )
    lead = await login(stack.api_url, {"email": "lead@example.test", "password": "Lead-Pass-123"})
    try:
        got = (await lead.get(f"/api/v1/orgs/{second['id']}")).json()
        assert got["role"] == "admin"
        resp = await lead.post(
            f"/api/v1/orgs/{second['id']}/members",
            json={
                "email": "boss@example.test",
                "role": "owner",
                "name": "B",
                "password": "Boss-Pass-123",
            },
        )
        assert resp.status_code == 403
        await stack.ok(
            "PATCH", f"/api/v1/orgs/{second['id']}/members/{added['user_id']}", {"role": "member"}
        )
        resp = await lead.patch(f"/api/v1/orgs/{second['id']}", json={"name": "Mine"})
        assert resp.status_code == 403
        members = await stack.ok("GET", f"/api/v1/orgs/{second['id']}/members")
        assert {m["role"] for m in members} == {"owner", "member"}
        await stack.ok(
            "DELETE", f"/api/v1/orgs/{second['id']}/members/{added['user_id']}", status=204
        )
        assert (await lead.get(f"/api/v1/orgs/{second['id']}")).status_code == 404
        me = (await stack.client.get("/api/v1/auth/me")).json()
        resp = await stack.client.delete(f"/api/v1/orgs/{second['id']}/members/{me['id']}")
        assert resp.status_code == 409
        assert (
            await stack.client.get(f"/api/v1/orgs/{second['id']}/audit-logs")
        ).status_code == 200
    finally:
        await lead.aclose()


async def test_project_members_and_notices(ready: Stack) -> None:
    mail.OUTBOX.clear()
    client, user_id = await ready.member("viewer")
    await client.aclose()
    notice = mail.OUTBOX[-1]
    assert notice.subject == "You were added to Shop"
    assert f"/projects/{ready.project_id}" in notice.text and "as viewer" in notice.text
    members = await ready.ok("GET", ready.p("/members"))
    assert {m["role"] for m in members} == {"admin", "viewer"}
    await ready.ok("PATCH", ready.p(f"/members/{user_id}"), {"role": "editor"})
    await ready.ok("DELETE", ready.p(f"/members/{user_id}"), status=204)
    me = (await ready.client.get("/api/v1/auth/me")).json()
    resp = await ready.client.delete(ready.p(f"/members/{me['id']}"))
    assert resp.status_code == 409


async def test_project_settings_github_token_and_limits(ready: Stack) -> None:
    out = await ready.ok(
        "PATCH",
        ready.p(),
        {
            "name": "Shop API",
            "github_repo": "euron-demo/python-shop",
            "github_token": "ghtoken-test-only",
            "run_cpu_s": 30,
            "run_memory_mb": 512,
        },
    )
    assert out["name"] == "Shop API" and out["has_github_token"] is True
    assert out["run_cpu_s"] == 30 and "ghtoken" not in str(out)
    entry = (await ready.audit(action="project.updated"))[0]
    assert "github_token" in entry["details"]["fields"] and "ghtoken" not in str(entry)
    # The sealed token is sent to GitHub as a bearer token (the mock lets private repos in).
    imp = await ready.import_github("euron-demo/private-thing")
    assert imp["status"] == "failed" and "no such repository" in imp["error"]
    cleared = await ready.ok("PATCH", ready.p(), {"github_token": "", "run_cpu_s": None})
    assert cleared["has_github_token"] is False and cleared["run_cpu_s"] is None
    bad = await ready.client.patch(ready.p(), json={"github_repo": "nope"})
    assert bad.status_code == 400
    listed = await ready.ok("GET", "/api/v1/projects")
    assert listed[0]["name"] == "Shop API"
    await ready.ok("DELETE", ready.p(), status=204)
    assert (await ready.client.get(ready.p())).status_code == 404


async def test_providers_default_disable_test_and_delete(ready: Stack) -> None:
    providers = await ready.ok("GET", ready.p("/providers"))
    assert [p["is_default"] for p in providers] == [True]
    gw = await ready.provider("gateway", "openai_compatible", is_default=True)
    listed = await ready.ok("GET", ready.p("/providers"))
    assert [(p["name"], p["is_default"]) for p in listed] == [("gateway", True), ("mock", False)]
    tested = await ready.ok("POST", ready.p(f"/providers/{gw['id']}/test"))
    assert tested["ok"] is True
    await ready.ok("PATCH", ready.p(f"/providers/{gw['id']}"), {"enabled": False})
    await ready.import_zip("python-shop")
    gen = await ready.generate(kinds=["unit"])
    assert gen["provider_kind"] == "mock"
    await ready.ok("DELETE", ready.p(f"/providers/{gw['id']}"), status=204)
    resp = await ready.client.post(
        ready.p("/providers"),
        json={"name": "meta", "kind": "openai_compatible", "base_url": "http://169.254.169.254/v1"},
    )
    assert resp.status_code == 422
    resp = await ready.client.post(
        ready.p("/providers"), json={"name": "x", "kind": "openai_compatible"}
    )
    assert resp.status_code == 400


async def test_sign_in_password_and_sign_out(stack: Stack) -> None:
    async with httpx.AsyncClient(base_url=stack.api_url, headers=CSRF) as c:
        bad = await c.post(
            "/api/v1/auth/login", json={"email": "admin@example.test", "password": "wrong"}
        )
        assert bad.status_code == 401
        assert (await c.get("/api/v1/auth/session")).json()["user"] is None
        ok = await c.post(
            "/api/v1/auth/login", json={"email": "admin@example.test", "password": "Admin-Pass-123"}
        )
        assert ok.status_code == 200
        assert (await c.get("/api/v1/auth/session")).json()["user"]["email"] == "admin@example.test"
        changed = await c.post(
            "/api/v1/auth/password",
            json={"current_password": "Admin-Pass-123", "new_password": "Admin-Pass-456"},
        )
        assert changed.status_code == 200
        out = await c.post("/api/v1/auth/logout")
        assert out.status_code == 200
        assert (await c.get("/api/v1/auth/me")).status_code == 401


async def test_request_guards(ready: Stack) -> None:
    resp = await ready.client.post(ready.p("/tests/generate"), json={"kinds": []})
    body = resp.json()
    assert resp.status_code == 422 and body["error"]["code"] == "validation_error"
    assert body["error"]["details"]["errors"][0]["loc"][-1] == "kinds"
    assert (await ready.client.get(ready.p("/runs/not-a-uuid"))).status_code == 422
    resp = await ready.client.get("/api/v1/projects/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
    async with httpx.AsyncClient(base_url=ready.api_url, headers=CSRF, timeout=60) as c:
        assert (await c.get(ready.p("/runs"))).status_code == 401
    resp = await ready.client.get("/api/v1/nothing-here")
    assert resp.status_code == 404 and resp.json()["error"]["code"] == "http_error"
    resp = await ready.client.post(ready.p("/runs"), json={"kind": "generated"})
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "no_import"
