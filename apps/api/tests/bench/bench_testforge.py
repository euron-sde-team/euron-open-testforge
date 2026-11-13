"""Benchmarks (make bench). Prints real numbers for the README.

1. Static analysis of a real-sized codebase: TestForge's own API source (Python) and the
   demo TypeScript project repeated, timed end to end (parse, units, untested check).
2. The assertion check: generated test files checked per second.
3. Generation overhead excluding model time: prompt build, the deterministic mock model,
   answer parsing and the check, for every unit of the demo Python project.
4. The sandbox (needs the integration sandbox on TESTFORGE_SANDBOX_PORT, make
   test-integration starts it): a one-test pytest run, cold and warm, and the demo
   project's suite with coverage. The overhead is wall time minus the test's own time.
"""

from __future__ import annotations

import base64
import statistics
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import httpx

from testforge.analysis import analyzer
from testforge.generation import checks, prompt
from testforge.providers.mock.responder import respond
from testforge.sandbox.protocol import RunRequest, RunResult, SandboxLimits, WorkspaceFile, sign
from tests.integration.conftest import SANDBOX_SECRET, SANDBOX_URL

ROOT = Path(__file__).parents[2]
DEMO = ROOT / "src" / "testforge" / "demo" / "projects"


def _files(root: Path, suffixes: tuple[str, ...]) -> dict[str, str]:
    return {
        str(p.relative_to(root)): p.read_text()
        for p in root.rglob("*")
        if p.is_file() and p.suffix in suffixes and "__pycache__" not in p.parts
    }


def bench_analysis() -> None:
    py = _files(ROOT / "src", (".py",))
    ts_one = _files(DEMO / "ts-toolkit", (".ts", ".json"))
    ts = {f"pkg{i}/{p}": t for i in range(40) for p, t in ts_one.items()}
    for label, files in (
        ("Python (TestForge's own API source)", py),
        ("TypeScript (demo x40)", ts),
    ):
        lines = sum(t.count("\n") for t in files.values())
        times = []
        for _ in range(5):
            started = time.perf_counter()
            result, _ = analyzer.analyze(files)
            times.append(time.perf_counter() - started)
        print(
            f"analysis {label}: {len(files)} files, {lines} lines, {len(result.units)} units: "
            f"median {statistics.median(times) * 1000:.0f} ms ({lines / statistics.median(times):,.0f} lines/s)"
        )


def _payloads() -> list[dict[str, object]]:
    a, _ = analyzer.analyze(_files(DEMO / "python-shop", (".py", ".txt")))
    classes = {u.name: [e.as_dict() for e in u.examples] for u in a.units if u.kind == "class"}
    out = []
    for u in a.units:
        row = SimpleNamespace(
            id=uuid.uuid4(),
            kind=u.kind,
            name=u.name,
            qualname=u.qualname,
            module=u.module,
            file=u.file,
            start_line=u.start_line,
            end_line=u.end_line,
            signature=u.signature,
            docstring=u.docstring,
            details=u.details(),
            source=u.source,
        )
        out.append(prompt.unit_payload(row, classes.get(u.class_name or u.name, []), 2000))
    return out


def bench_generation_and_check() -> None:
    units = _payloads()
    req = {
        "mode": "unit",
        "framework": "pytest",
        "kinds": ["unit", "edge", "negative"],
        "units": units,
    }
    times = []
    tests: list[prompt.ParsedTest] = []
    for _ in range(20):
        started = time.perf_counter()
        system, user = prompt.build(req)
        tests = prompt.parse_answer(respond(system, user))
        by_id = {u["id"]: u for u in units}
        for t in tests:
            u = by_id[t.target]
            checks.check("python", t.code, {str(u["name"]), str(u.get("class_name") or u["name"])})
        times.append(time.perf_counter() - started)
    print(
        f"generation overhead (no model time): {len(units)} units, {len(tests)} tests written and "
        f"checked: median {statistics.median(times) * 1000:.1f} ms"
    )
    codes = [t.code for t in tests] * 50
    started = time.perf_counter()
    for code in codes:
        checks.check("python", code, {"split_bill", "reserve", "Cart"})
    elapsed = time.perf_counter() - started
    print(
        f"assertion check: {len(codes)} files in {elapsed * 1000:.0f} ms ({len(codes) / elapsed:,.0f} files/s)"
    )


def _run(files: dict[str, bytes], coverage: bool) -> tuple[float, RunResult]:
    req = RunRequest(
        job_id=uuid.uuid4().hex,
        runner="pytest",
        files=[
            WorkspaceFile(path=p, content_b64=base64.b64encode(c).decode())
            for p, c in files.items()
        ],
        coverage=coverage,
        limits=SandboxLimits(cpu_s=60, wall_s=120),
    )
    body = req.model_dump_json().encode()
    started = time.perf_counter()
    resp = httpx.post(
        f"{SANDBOX_URL}/v1/runs",
        content=body,
        headers={"x-tf-sandbox": sign(SANDBOX_SECRET, body), "content-type": "application/json"},
        timeout=200,
    )
    elapsed = time.perf_counter() - started
    resp.raise_for_status()
    return elapsed, RunResult.model_validate_json(resp.content)


def bench_sandbox() -> None:
    try:
        httpx.get(f"{SANDBOX_URL}/healthz", timeout=3).raise_for_status()
    except httpx.HTTPError:
        print(f"sandbox: not reachable on {SANDBOX_URL} (run make test-integration first); skipped")
        return
    one = {"tests/test_one.py": b"def test_one():\n    assert 1 + 1 == 2\n"}
    cold, _ = _run(one, coverage=False)
    warm = [_run(one, coverage=False)[0] for _ in range(10)]
    print(
        f"sandbox: one-test pytest run, round trip from the worker: first {cold * 1000:.0f} ms, "
        f"then median {statistics.median(warm) * 1000:.0f} ms (nsjail, a fresh interpreter, pytest start)"
    )
    shop = {
        str(p.relative_to(DEMO / "python-shop")): p.read_bytes()
        for p in (DEMO / "python-shop").rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    }
    runs = [_run(shop, coverage=True) for _ in range(5)]
    print(
        f"sandbox: demo project suite with coverage: median {statistics.median(r[0] for r in runs) * 1000:.0f} ms "
        f"round trip, {statistics.median(r[1].cpu_ms for r in runs):.0f} ms CPU, "
        f"peak {statistics.median(r[1].memory_kb for r in runs) / 1024:.0f} MB"
    )


if __name__ == "__main__":
    bench_analysis()
    bench_generation_and_check()
    bench_sandbox()
