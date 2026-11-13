"""The Python SDK and the CLI against the live test API, sandbox included."""

from __future__ import annotations

import asyncio
import io
from contextlib import redirect_stdout
from pathlib import Path

import pytest
from euron_testforge import AsyncTestForge, TestForge, TestForgeError
from euron_testforge.cli import main

from tests.integration.conftest import Stack, demo_zip

pytestmark = pytest.mark.integration


async def _key(stack: Stack, scopes: list[str]) -> str:
    out = await stack.ok(
        "POST", stack.p("/api-keys"), {"name": "sdk", "scopes": scopes}, status=201
    )
    return str(out["key"])


async def test_the_sync_client_end_to_end(ready: Stack, tmp_path: Path) -> None:
    key = await _key(ready, ["read", "generate", "execute", "manage"])
    archive = tmp_path / "python-shop.zip"
    archive.write_bytes(demo_zip("python-shop"))

    def flow() -> None:
        with TestForge(url=ready.api_url, api_key=key) as tf:
            imp = tf.import_zip(archive)
            assert imp.ready and imp.languages == ["python"] and imp.units > 10
            assert tf.analysis()["untested"] > 5
            gen = tf.generate(["unit"])
            assert gen.status == "done" and gen.accepted_count > 5 and gen.rejected_count >= 1
            tests = tf.tests(generation_id=gen.id)
            assert "split_bill" in tf.test_code(next(t.id for t in tests if "split_bill" in t.name))
            assert tf.accept([t.id for t in tests]) == len(tests)
            run = tf.run()
            assert run.finished and not run.ok and run.failed == 1
            assert run.failures[0].expected == "[33.34, 33.33, 33.33]"
            assert tf.get_run(run.id).id == run.id and tf.runs()[0].id == run.id
            assert tf.coverage()["latest"]["run_id"] == run.id
            assert b"Failures, explained" in tf.report("run", "html", run.id)
            assert tf.imports()[0].id == imp.id
            pull = tf.import_github("euron-demo/python-shop")
            assert pull.ready
            with pytest.raises(TestForgeError) as err:
                tf.import_github("not a repo")
            assert err.value.status == 400 and err.value.code == "invalid_repo"

    await asyncio.to_thread(flow)


async def test_the_async_client(ready: Stack) -> None:
    key = await _key(ready, ["read", "generate", "execute", "manage"])
    async with AsyncTestForge(url=ready.api_url, api_key=key) as tf:
        imp = await tf.import_github("euron-demo/ts-toolkit")
        assert imp.ready and imp.languages == ["typescript"]
        assert (await tf.analysis())["units"] > 10
        gen = await tf.generate(["unit"])
        tests = await tf.tests(generation_id=gen.id)
        assert await tf.accept([t.id for t in tests]) == len(tests)
        run = await tf.run()
        assert run.ok, run.raw
        assert (await tf.get_run(run.id)).status == "passed"
        assert (await tf.coverage())["latest"]["tool"] == "istanbul"


async def test_the_cli_in_ci(ready: Stack) -> None:
    key = await _key(ready, ["read", "generate", "execute", "manage"])
    base = ["--url", ready.api_url, "--api-key", key]

    def cli(*args: str) -> tuple[int, str]:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main([*base, *args])
        return code, buf.getvalue()

    def flow() -> None:
        code, out = cli("import-github", "euron-demo/python-shop")
        assert code == 0 and "ready python" in out
        code, out = cli("analysis")
        assert code == 0 and "untested" in out
        code, out = cli("generate", "--kinds", "unit,negative", "--pull", "12")
        assert code == 0 and "tests written" in out
        code, out = cli("accept", "--all")
        assert code == 0 and "accepted" in out
        code, out = cli("run")
        assert code == 1 and "FAILED" in out and "33.34" in out
        code, out = cli("coverage")
        assert code == 0 and "line coverage" in out
        code, out = cli("tests", "--status", "accepted")
        assert code == 0 and "accepted" in out
        code, out = cli("run", "--kind", "project")
        assert code == 0 and "passed" in out
        code, out = cli("report", "--format", "csv")
        assert code == 0 and out.startswith("started,run")

    await asyncio.to_thread(flow)
    code = await asyncio.to_thread(
        main, ["--url", ready.api_url, "--api-key", "tfk_000000000000_bad", "analysis"]
    )
    assert code == 2
