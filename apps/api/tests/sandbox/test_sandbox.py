"""The sandbox, for real: nsjail, pytest and Vitest inside the hardened sandbox image.

Covers running real projects with real coverage, capturing actual and expected values in
the same run (A8), no network (A3), no access outside the workspace (A4), and every limit
stopping a run and being reported by name (A5), with the sandbox healthy afterwards.
"""

from __future__ import annotations

import json
import time

from tests.sandbox.conftest import Run, hostile, project_files

SECRET = "test-only-sandbox-secret-that-must-never-leak"


def _tests(result: object) -> dict[str, dict[str, object]]:
    report = json.loads(result.report or "{}")  # type: ignore[attr-defined]
    return {t["name"]: t for t in report.get("tests", [])}


# ── Real projects ────────────────────────────────────────────────────────────────────


def test_python_project_suite_runs_with_real_coverage(run: Run) -> None:
    result = run("pytest", project_files("python-shop"), coverage=True)
    assert result.error is None, result.error
    assert result.limit_exceeded is None
    assert result.exit_code == 0, result.stdout_tail + result.stderr_tail
    tests = _tests(result)
    assert {t["outcome"] for t in tests.values()} == {"passed"}
    assert len(tests) == 2
    coverage = json.loads(result.coverage or "{}")
    assert coverage["totals"]["num_statements"] > 0
    assert "app/pricing.py" in coverage["files"]
    # The project's own tests touch only pricing: inventory is measured, and uncovered.
    assert coverage["files"]["app/inventory.py"]["summary"]["covered_lines"] == 0
    assert result.coverage_tool == "coverage.py"


def test_python_failure_keeps_actual_and_expected_from_the_same_run(run: Run) -> None:
    files = project_files("python-shop")
    files["tests/testforge/test_split.py"] = (
        b"from app.pricing import split_bill\n\n\n"
        b"def test_split_bill_adds_up():\n"
        b"    assert split_bill(100.0, 3) == [33.34, 33.33, 33.33]\n"
    )
    result = run("pytest", files, targets=["tests/testforge"], coverage=True)
    case = _tests(result)["test_split_bill_adds_up"]
    assert case["outcome"] == "failed"
    compare = case["failure"]["compare"]
    assert compare["operator"] == "=="
    assert compare["left"] == "[33.33, 33.33, 33.33]"
    assert compare["right"] == "[33.34, 33.33, 33.33]"
    assert case["failure"]["line"] == 5


def test_typescript_project_runs_with_istanbul_coverage(run: Run) -> None:
    files = project_files("ts-toolkit")
    files["testforge/clamp.test.ts"] = (
        b'import { expect, it } from "vitest";\n'
        b'import { clamp } from "../src/validate";\n\n'
        b'it("clamps", () => {\n  expect(clamp(15, 0, 10)).toBe(10);\n});\n'
        b'it("is wrong on purpose", () => {\n  expect(clamp(-2, 0, 10)).toBe(3);\n});\n'
    )
    result = run("vitest", files, coverage=True)
    assert result.error is None, result.error
    assert result.limit_exceeded is None, result.limit_detail + result.stderr_tail
    tests = _tests(result)
    assert tests["formatPrice > formats dollars"]["outcome"] == "passed"
    assert tests["clamps"]["outcome"] == "passed"
    wrong = tests["is wrong on purpose"]
    assert wrong["outcome"] == "failed"
    assert wrong["failure"]["compare"]["left"] == "0"
    assert wrong["failure"]["compare"]["right"] == "3"
    coverage = json.loads(result.coverage or "{}")
    assert any(path.endswith("src/validate.ts") for path in coverage), (
        sorted(coverage)[:20],
        result.coverage is None,
        result.stderr_tail[-1500:],
    )
    assert result.coverage_tool == "istanbul"


# ── A3: no network ───────────────────────────────────────────────────────────────────


def test_python_run_has_no_network(run: Run) -> None:
    result = run("pytest", {"tests/test_network.py": hostile("network_probe.py")}, wall_s=60)
    tests = _tests(result)
    for name in (
        "test_tcp_to_the_internet",
        "test_dns_lookup",
        "test_http_request",
        "test_platform_services",
        "test_cloud_metadata_service",
    ):
        assert tests[name]["outcome"] == "failed", name
        message = str(tests[name]["failure"]["message"])
        assert any(
            word in message
            for word in (
                "unreachable",
                "Name or service not known",
                "resolution",
                "URLError",
                "Errno",
            )
        ), (name, message)
    assert tests["test_only_loopback_is_up"]["outcome"] == "passed", tests[
        "test_only_loopback_is_up"
    ]


def test_typescript_run_has_no_network(run: Run) -> None:
    files = {"package.json": b"{}", "net.test.ts": hostile("network_probe.ts")}
    result = run("vitest", files, wall_s=60)
    tests = _tests(result)
    assert tests["fetches from the internet"]["outcome"] == "failed"
    assert tests["opens a socket to the platform database"]["outcome"] == "failed"


# ── A4: nothing outside the workspace ────────────────────────────────────────────────


def test_run_sees_nothing_outside_its_workspace(run: Run, runs: object) -> None:
    other = runs.root / "another-project-run" / "box"  # type: ignore[attr-defined]
    other.mkdir(parents=True, exist_ok=True)
    (other / "secret.txt").write_text("another project's file")
    try:
        result = run("pytest", {"tests/test_escape.py": hostile("escape_probe.py")})
    finally:
        (other / "secret.txt").unlink()
    tests = _tests(result)
    assert tests["test_environment_holds_no_secret"]["outcome"] == "passed"
    assert tests["test_runs_as_nobody"]["outcome"] == "passed"
    for name, t in tests.items():
        if name.startswith(("test_read_", "test_write_")):
            assert t["outcome"] == "failed", name
    # The links the run planted were not followed: nothing of the service came back.
    assert result.events == ""
    assert SECRET not in result.model_dump_json()
    assert "another project's file" not in result.model_dump_json()


# ── A5: limits stop the run and are named ────────────────────────────────────────────


class _Timed:
    def __init__(self, result: object, elapsed: float) -> None:
        self.result = result
        self.elapsed = elapsed

    def __getattr__(self, name: str) -> object:
        return getattr(self.result, name)


def _limit_run(run: Run, test: str, **limits: int) -> object:
    started = time.monotonic()
    result = run(
        "pytest",
        {"tests/test_limits.py": hostile("limits_probe.py")},
        targets=[f"tests/test_limits.py::{test}"],
        **limits,
    )
    return _Timed(result, time.monotonic() - started)


def test_cpu_limit(run: Run) -> None:
    r = _limit_run(run, "test_spin_forever", cpu_s=2, wall_s=30)
    assert r.limit_exceeded == "cpu", (r.limit_detail, r.signal, r.cpu_ms)  # type: ignore[attr-defined]
    assert r.elapsed < 15  # type: ignore[attr-defined]


def test_wall_clock_limit(run: Run) -> None:
    r = _limit_run(run, "test_sleep_forever", cpu_s=30, wall_s=3)
    assert r.limit_exceeded == "wall_clock"  # type: ignore[attr-defined]
    assert r.elapsed < 12  # type: ignore[attr-defined]
    # The test that was running when the run stopped is in the event log.
    assert "test_sleep_forever" in r.events  # type: ignore[attr-defined]


def test_memory_limit(run: Run) -> None:
    r = _limit_run(run, "test_allocate_four_gigabytes", memory_mb=256)
    assert r.limit_exceeded == "memory", r.limit_detail  # type: ignore[attr-defined]


def test_output_limit(run: Run) -> None:
    r = _limit_run(run, "test_flood_output", output_bytes=1_000_000)
    assert r.limit_exceeded == "output", (r.limit_detail, r.stderr_tail[-500:])  # type: ignore[attr-defined]


def test_process_limit(run: Run) -> None:
    r = _limit_run(run, "test_start_ten_thousand_threads")
    assert r.limit_exceeded == "processes", (r.limit_detail, r.stdout_tail[-800:])  # type: ignore[attr-defined]


def test_typescript_cpu_or_wall_limit(run: Run) -> None:
    files = {"package.json": b"{}", "spin.test.ts": hostile("spin_probe.ts")}
    started = time.monotonic()
    r = run("vitest", files, cpu_s=3, wall_s=20)
    assert r.limit_exceeded in ("cpu", "wall_clock"), r.limit_detail
    assert time.monotonic() - started < 40


def test_typescript_memory_limit(run: Run) -> None:
    files = {"package.json": b"{}", "heap.test.ts": hostile("heap_probe.ts")}
    r = run("vitest", files, memory_mb=256, wall_s=60)
    assert r.limit_exceeded == "memory", (r.limit_detail, r.stderr_tail[-600:])


def test_sandbox_still_works_after_every_limit(run: Run) -> None:
    result = run("pytest", project_files("python-shop"))
    assert result.exit_code == 0
    assert result.limit_exceeded is None


def test_a_workspace_path_cannot_leave_the_box(run: Run) -> None:
    result = run("pytest", {".testforge/report.json": b"{}"})
    assert result.error is not None
    assert "reserved" in result.error
