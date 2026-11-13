"""API tests from an OpenAPI document (A7), pull request scoping (A9) and the inbound
GitHub webhook."""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from tests.integration.conftest import DEMO, Stack

pytestmark = pytest.mark.integration


async def test_api_tests_cover_every_documented_operation(shop: Stack) -> None:
    """A7: every operation gets a test, with its status code and response shape."""
    spec = await shop.ok(
        "POST",
        shop.p("/specs"),
        {"document": (DEMO / "python-shop-openapi.json").read_text()},
        status=201,
    )
    assert spec["operation_count"] == 4
    keys = {op["key"] for op in spec["operations"]}
    gen = await shop.generate(kinds=["api"], spec_id=spec["id"])
    assert gen["status"] == "done", gen
    assert set(gen["operations_covered"]) == keys
    tests = await shop.tests(generation_id=gen["id"])
    covered = {t["operation"] for t in tests}
    assert covered == keys
    by_op = {t["operation"]: t for t in tests if t["kind"] == "api"}
    product = await shop.ok("GET", shop.p(f"/tests/{by_op['GET /products/{product_id}']['id']}"))
    assert "response.status_code in (200, 404, 422)" in product["code"]
    assert "set(['id', 'name', 'price']) <= set(body)" in product["code"]
    listing = await shop.ok("GET", shop.p(f"/tests/{by_op['GET /products']['id']}"))
    assert "isinstance(body, list)" in listing["code"]
    await shop.accept_all(gen["id"])
    run = await shop.run(kind="generated")
    assert run["status"] == "passed", run
    assert run["passed"] == len(tests)


async def test_a_yaml_document_works_and_a_bad_one_is_refused(shop: Stack) -> None:
    yaml_doc = (
        "openapi: 3.0.3\ninfo: {title: Mini, version: '1'}\npaths:\n  /health:\n"
        "    get:\n      responses:\n        '200': {description: ok}\n"
    )
    spec = await shop.ok("POST", shop.p("/specs"), {"document": yaml_doc}, status=201)
    assert spec["operations"][0]["key"] == "GET /health"
    bad = await shop.client.post(shop.p("/specs"), json={"document": '{"swagger": "2.0"}'})
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "invalid_spec"


async def test_api_generation_needs_an_app(ready: Stack) -> None:
    await ready.import_zip("ts-toolkit")
    spec = await ready.ok(
        "POST",
        ready.p("/specs"),
        {"document": (DEMO / "python-shop-openapi.json").read_text()},
        status=201,
    )
    resp = await ready.client.post(
        ready.p("/tests/generate"), json={"kinds": ["api"], "spec_id": spec["id"]}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "no_app"


async def test_pull_request_scopes_generation_to_the_changed_code(ready: Stack) -> None:
    """A9: changed files between base and head, and only the units they touch."""
    await ready.ok("PATCH", ready.p(), {"github_repo": "https://github.com/euron-demo/python-shop"})
    await ready.import_github("euron-demo/python-shop")
    pull = await ready.ok(
        "POST", ready.p("/pulls"), {"number": 12}, status=202, params={"wait": 60}
    )
    assert pull["status"] == "ready", pull
    assert pull["base_sha"] != pull["head_sha"]
    changed = {f["path"]: f for f in pull["changed_files"]}
    assert set(changed) == {"app/pricing.py", "app/inventory.py"}
    assert changed["app/inventory.py"]["changed_lines"]
    scoped = {u["qualname"] for u in pull["scoped_units"]}
    assert scoped == {"app.pricing.split_bill", "app.inventory.restock_plan"}
    gen = await ready.generate(kinds=["unit", "negative"], pull_id=pull["id"])
    assert gen["status"] == "done", gen
    assert set(gen["unit_ids"]) == set(pull["scoped_unit_ids"])
    tests = await ready.tests(generation_id=gen["id"])
    assert tests
    assert {t["unit_id"] for t in tests} <= set(pull["scoped_unit_ids"])
    # Importing the same head again is idempotent.
    again = await ready.ok("POST", ready.p("/pulls"), {"number": 12}, status=202)
    assert again["id"] == pull["id"]


async def test_typescript_pull_request(ready: Stack) -> None:
    await ready.ok("PATCH", ready.p(), {"github_repo": "euron-demo/ts-toolkit"})
    pull = await ready.ok("POST", ready.p("/pulls"), {"number": 4}, status=202, params={"wait": 60})
    assert [u["qualname"] for u in pull["scoped_units"]] == ["src/slug.truncate"]


def _signed(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


async def test_github_webhook_imports_an_opened_pull_request(ready: Stack) -> None:
    hook = await ready.ok("POST", ready.p("/github/webhook-secret"))
    assert hook["url"].endswith(f"/api/v1/hooks/github/{ready.project_id}")
    event = {
        "action": "opened",
        "number": 12,
        "pull_request": {"number": 12},
        "repository": {"full_name": "euron-demo/python-shop"},
    }
    body = json.dumps(event).encode()
    url = f"/api/v1/hooks/github/{ready.project_id}"
    unsigned = await ready.client.post(
        url, content=body, headers={"x-github-event": "pull_request"}
    )
    assert unsigned.status_code == 401
    forged = await ready.client.post(
        url,
        content=body,
        headers={"x-github-event": "pull_request", "x-hub-signature-256": _signed("wrong", body)},
    )
    assert forged.status_code == 401
    ok = await ready.client.post(
        url,
        content=body,
        headers={
            "x-github-event": "pull_request",
            "x-hub-signature-256": _signed(hook["secret"], body),
        },
    )
    assert ok.status_code == 202, ok.text
    assert ok.json()["accepted"] is True
    pulls = await ready.ok("GET", ready.p("/pulls"))
    assert pulls[0]["source"] == "webhook" and pulls[0]["number"] == 12
    closed = json.dumps({**event, "action": "closed"}).encode()
    ignored = await ready.client.post(
        url,
        content=closed,
        headers={
            "x-github-event": "pull_request",
            "x-hub-signature-256": _signed(hook["secret"], closed),
        },
    )
    assert ignored.json()["accepted"] is False
