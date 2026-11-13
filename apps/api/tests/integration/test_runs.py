"""Runs in the real sandbox: a passing suite with real coverage (A1), a failure explained
from the same run (A8), and an uploaded project's own suite that tries to reach the
network (A3), read outside its workspace (A4) and cross every limit (A5)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration.conftest import Stack

pytestmark = pytest.mark.integration
HOSTILE = Path(__file__).parents[1] / "sandbox" / "hostile"


async def test_generate_accept_run_and_measure_coverage(shop: Stack) -> None:
    """A1 through the API: import, generate, accept, run, real coverage."""
    gen = await shop.generate(kinds=["unit", "edge", "negative"])
    accepted = await shop.accept_all(gen["id"])
    run = await shop.run(kind="generated")
    assert run["status"] == "failed", run  # split_bill's documented example exposes its bug
    assert run["passed"] >= len(accepted) - 2
    assert run["failed"] == 1
    assert run["limit_exceeded"] is None
    assert run["coverage_percent"] is not None and run["coverage_percent"] > 40
    assert run["cpu_ms"] > 0 and run["memory_kb"] > 0
    cov = await shop.ok("GET", shop.p(f"/runs/{run['id']}/coverage"))
    assert cov["tool"] == "coverage.py"
    files = {f["path"]: f for f in cov["files"]}
    assert files["app/pricing.py"]["percent"] > 80
    assert files["app/pricing.py"]["lines_total"] > 0
    project = await shop.ok("GET", shop.p("/coverage"))
    assert project["latest"]["run_id"] == run["id"]
    # Tests that passed are marked so in the test list.
    outcomes = {t["name"]: t["last_outcome"] for t in await shop.tests(status="accepted")}
    assert outcomes["test_split_bill_examples"] == "failed"
    assert outcomes["test_add_tax_examples"] == "passed"


async def test_failure_is_explained_from_the_same_run(shop: Stack) -> None:
    """A8: actual, expected and the assertion, without a second execution."""
    gen = await shop.generate(kinds=["unit"])
    split = next(t for t in await shop.tests(generation_id=gen["id"]) if "split_bill" in t["name"])
    run = await shop.run(kind="generated", test_ids=[split["id"]])
    failed = [c for c in run["cases"] if c["outcome"] == "failed"]
    assert len(failed) == 1
    f = failed[0]["failure"]
    assert f["kind"] == "assertion"
    assert f["actual"] == "[33.33, 33.33, 33.33]"
    assert f["expected"] == "[33.34, 33.33, 33.33]"
    assert f["operator"] == "=="
    assert "split_bill(100.0, 3)" in f["expression"]
    assert "add up to 99.99 instead of 100.0" in f["explanation"]
    explained = await shop.ok(
        "POST",
        shop.p("/bugs/analyze"),
        {"run_id": run["id"], "case_id": failed[0]["id"], "use_model": True},
    )
    assert explained["failure"]["actual"] == f["actual"]
    assert "[33.33, 33.33, 33.33]" in explained["model_explanation"]
    # One execution: the run's sandbox time was spent once, and no other run exists.
    runs = await shop.ok("GET", shop.p("/runs"))
    assert len(runs) == 1


async def test_project_suite_runs_in_the_sandbox(shop: Stack) -> None:
    run = await shop.run(kind="project")
    assert run["status"] == "passed", run
    assert run["passed"] == 2
    assert run["coverage_percent"] is not None


async def test_typescript_project_runs_with_vitest(ready: Stack) -> None:
    await ready.import_zip("ts-toolkit")
    gen = await ready.generate(kinds=["unit", "negative"])
    assert gen["accepted_count"] > 5
    await ready.accept_all(gen["id"])
    run = await ready.run(kind="all")
    assert run["framework"] == "vitest"
    assert run["status"] == "passed", run
    assert run["passed"] >= gen["accepted_count"]
    cov = await ready.ok("GET", ready.p(f"/runs/{run['id']}/coverage"))
    assert cov["tool"] == "istanbul"
    assert any(f["path"] == "src/validate.ts" and f["percent"] == 100 for f in cov["files"])


async def _hostile_run(stack: Stack, probe: str, **params: object) -> dict[str, object]:
    imp = await stack.import_zip(
        "python-shop", extra={f"tests/test_{probe}.py": (HOSTILE / f"{probe}_probe.py").read_text()}
    )
    assert imp["status"] == "ready"
    return await stack.run(kind="project", **params)  # type: ignore[arg-type]


async def test_uploaded_suite_has_no_network(shop: Stack) -> None:
    """A3: an uploaded project's own tests cannot reach anything."""
    run = await _hostile_run(shop, "network")
    cases = {c["name"]: c for c in run["cases"]}  # type: ignore[union-attr]
    for name in (
        "test_tcp_to_the_internet",
        "test_dns_lookup",
        "test_platform_services",
        "test_cloud_metadata_service",
    ):
        assert cases[name]["outcome"] == "failed", name
        assert (
            "unreachable" in cases[name]["message"] or "name resolution" in cases[name]["message"]
        )
    assert cases["test_only_loopback_is_up"]["outcome"] == "passed"


async def test_uploaded_suite_sees_nothing_outside_its_workspace(shop: Stack) -> None:
    """A4: no credentials, no other files, nothing of the platform."""
    run = await _hostile_run(shop, "escape")
    cases = {c["name"]: c for c in run["cases"]}  # type: ignore[union-attr]
    assert cases["test_environment_holds_no_secret"]["outcome"] == "passed"
    for name, case in cases.items():
        if name.startswith(("test_read_", "test_write_")):
            assert case["outcome"] == "failed", name
    assert shop.settings.sandbox_secret not in str(run)
    assert shop.settings.session_secret not in str(run)


@pytest.mark.parametrize(
    ("test", "limit", "budget"),
    [
        ("test_spin_forever", "cpu", {"run_cpu_s": 2, "run_wall_s": 60}),
        ("test_sleep_forever", "wall_clock", {"run_wall_s": 4}),
        ("test_allocate_four_gigabytes", "memory", {"run_memory_mb": 256}),
        ("test_flood_output", "output", {"run_output_bytes": 1_000_000}),
    ],
)
async def test_limits_stop_the_run_and_are_named(
    shop: Stack, test: str, limit: str, budget: dict[str, int]
) -> None:
    """A5: the run is stopped, reported with the limit it crossed, never left running."""
    await shop.ok("PATCH", shop.p(), budget)
    probe = (HOSTILE / "limits_probe.py").read_text()
    only = (
        probe.split("\n\n\ndef ")[0]
        + "\n\n\ndef "
        + next(part for part in probe.split("\n\n\ndef ") if part.startswith(test))
    )
    await shop.import_zip("python-shop", extra={"tests/test_limits.py": only})
    run = await shop.run(kind="project", wait=120)
    assert run["status"] == "limit_exceeded", run
    assert run["limit_exceeded"] == limit
    assert run["message"]
    assert run["finished_at"] is not None
    if limit == "wall_clock":
        assert run["wall_ms"] < 15_000
        stopped = [c for c in run["cases"] if c["name"].endswith("test_sleep_forever")]
        assert stopped and stopped[0]["failure"]["kind"] == "limit"
    # The sandbox is fine afterwards.
    await shop.ok("PATCH", shop.p(), dict.fromkeys(budget))
    await shop.import_zip("python-shop")
    again = await shop.run(kind="project")
    assert again["status"] == "passed", again
