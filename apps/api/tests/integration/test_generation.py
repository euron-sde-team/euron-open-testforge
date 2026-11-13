"""Test generation (A2, A12): grounded tests through every provider, placeholders refused."""

from __future__ import annotations

import httpx
import pytest

from tests.integration.conftest import Stack

pytestmark = pytest.mark.integration


async def test_generated_tests_have_real_grounded_assertions(shop: Stack) -> None:
    """A2: every stored test asserts something about the code, from the code."""
    gen = await shop.generate(kinds=["unit", "edge", "negative"])
    assert gen["status"] == "done", gen
    assert gen["accepted_count"] > 10
    tests = await shop.tests(generation_id=gen["id"])
    assert len(tests) == gen["accepted_count"]
    for t in tests:
        assert t["status"] == "proposed"
        assert t["assertions"], t["name"]
        assert all("assert True" not in a["text"] for a in t["assertions"])
        assert t["description"]
    split = next(t for t in tests if t["name"] == "test_split_bill_examples")
    detail = await shop.ok("GET", shop.p(f"/tests/{split['id']}"))
    # The expected value is the one the function's own docstring documents.
    assert "assert split_bill(100.0, 3) == [33.34, 33.33, 33.33]" in detail["code"]
    assert detail["unit"]["qualname"] == "app.pricing.split_bill"
    assert detail["file_path"].startswith("tests/testforge/test_split_bill")
    kinds = {t["kind"] for t in tests}
    assert {"unit", "edge", "negative"} <= kinds


async def test_tests_without_assertions_are_refused_before_anyone_sees_them(shop: Stack) -> None:
    """A2: the mock writes an assertion-less call for units it cannot ground; refused."""
    gen = await shop.generate(kinds=["unit"])
    assert gen["rejected_count"] >= 1
    reasons = {r["code"] for r in gen["rejections"]}
    assert "no_assertion" in reasons
    names = {t["name"] for t in await shop.tests(generation_id=gen["id"])}
    assert not names & {r["name"] for r in gen["rejections"]}


async def test_a_careless_model_gets_nothing_through(shop: Stack) -> None:
    """A2 through a real adapter: placeholders, and assertions after a return, refused."""
    provider = await shop.provider(
        "careless", "openai_compatible", model="mock-placeholder", is_default=False
    )
    gen = await shop.generate(kinds=["unit"], provider_id=provider["id"])
    assert gen["status"] == "done", gen
    assert gen["accepted_count"] == 0
    assert gen["rejected_count"] >= 1
    assert all(r["code"] == "no_assertion" for r in gen["rejections"])


@pytest.mark.parametrize("kind", ["openai", "anthropic", "gemini", "ollama", "openai_compatible"])
async def test_every_provider_adapter_generates_the_same_tests(shop: Stack, kind: str) -> None:
    """A12: each real adapter speaks its wire format to the mock server, with the sealed key."""
    provider = await shop.provider(f"p-{kind}", kind, is_default=False)
    assert provider["has_api_key"] is True
    assert "secret" not in str(provider)
    gen = await shop.generate(kinds=["unit"], provider_id=provider["id"])
    assert gen["status"] == "done", gen
    assert gen["accepted_count"] > 5
    assert gen["input_tokens"] > 0
    async with httpx.AsyncClient() as http:
        auth = (await http.get(f"{shop.mock_ai_url}/_mock/auth")).json()
    family = {"openai": "v1", "openai_compatible": "v1"}.get(kind, kind)
    assert f"sk-p-{kind}-secret" in auth[family]


async def test_no_provider_means_no_generation(ready: Stack) -> None:
    """A12: real providers are off until configured; without any, generation says so."""
    await ready.project("Bare")
    await ready.import_zip("python-shop")
    resp = await ready.client.post(ready.p("/tests/generate"), json={"kinds": ["unit"]})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "no_provider"


async def test_provider_failure_is_reported(shop: Stack) -> None:
    provider = await shop.provider("flaky", "openai", is_default=False)
    async with httpx.AsyncClient() as http:
        await http.post(f"{shop.mock_ai_url}/_mock/fail", params={"status": 401, "times": 5})
    gen = await shop.generate(kinds=["unit"], provider_id=provider["id"])
    assert gen["status"] == "failed"
    assert gen["error_code"] == "provider_auth"


async def test_review_and_regenerate(shop: Stack) -> None:
    gen = await shop.generate(kinds=["unit"])
    tests = await shop.tests(generation_id=gen["id"])
    first = tests[0]
    accepted = await shop.ok("PATCH", shop.p(f"/tests/{first['id']}"), {"status": "accepted"})
    assert accepted["status"] == "accepted"
    again = await shop.ok(
        "POST", shop.p(f"/tests/{first['id']}/regenerate"), status=202, params={"wait": 60}
    )
    assert again["status"] == "done"
    old = await shop.ok("GET", shop.p(f"/tests/{first['id']}"))
    assert old["status"] == "discarded"
    bulk = await shop.ok(
        "POST",
        shop.p("/tests/review"),
        {"ids": [t["id"] for t in tests[1:4]], "status": "discarded"},
    )
    assert bulk["changed"] == 3
