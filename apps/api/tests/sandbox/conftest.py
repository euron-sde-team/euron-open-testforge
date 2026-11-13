"""The sandbox suite: real nsjail, real pytest and Vitest, inside the sandbox image with
the same hardening production gives the sandbox service (make test-sandbox).

Every test here builds a workspace, runs it through ``Runs.execute_sync`` (the code path
the service uses for every request) and checks what came back.
"""

from __future__ import annotations

import base64
import os
import uuid
from collections.abc import Callable
from pathlib import Path

import pytest

from testforge.core.config import Settings
from testforge.sandbox.protocol import RunRequest, RunResult, SandboxLimits, WorkspaceFile
from testforge.sandbox.server import Runs

HERE = Path(__file__).parent
DEMO = HERE.parents[1] / "src" / "testforge" / "demo" / "projects"
HOSTILE = HERE / "hostile"

pytestmark = pytest.mark.sandbox


def _skip_unless_image() -> None:
    if not os.path.exists("/usr/local/bin/nsjail") or not os.path.isdir("/opt/toolchain"):
        pytest.skip("needs the sandbox image (make test-sandbox)")


def project_files(name: str) -> dict[str, bytes]:
    root = DEMO / name
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    }


@pytest.fixture(scope="session")
def runs() -> Runs:
    _skip_unless_image()
    settings = Settings(
        sandbox_work_dir="/tmp/testforge-sandbox-tests",
        sandbox_secret="test-only-sandbox-secret-that-must-never-leak",
    )
    r = Runs(settings)
    r.root.mkdir(parents=True, exist_ok=True)
    return r


Run = Callable[..., RunResult]


@pytest.fixture
def run(runs: Runs) -> Run:
    def go(
        runner: str,
        files: dict[str, bytes | str],
        *,
        targets: list[str] | None = None,
        coverage: bool = False,
        **limits: int,
    ) -> RunResult:
        job = uuid.uuid4().hex
        req = RunRequest(
            job_id=job,
            runner=runner,  # type: ignore[arg-type]
            files=[
                WorkspaceFile(
                    path=p,
                    content_b64=base64.b64encode(c.encode() if isinstance(c, str) else c).decode(),
                )
                for p, c in files.items()
            ],
            targets=targets or [],
            coverage=coverage,
            limits=SandboxLimits(**{"cpu_s": 30, "wall_s": 60, **limits}),
        )
        workdir = runs.root / job
        workdir.mkdir(parents=True)
        try:
            return runs.execute_sync(req, workdir)
        finally:
            import shutil

            shutil.rmtree(workdir, ignore_errors=True)

    return go


def hostile(name: str) -> str:
    return (HOSTILE / name).read_text()
