"""Developer helper: run one workspace in the sandbox image and print what came back.

docker run ... testforge-sandbox-test:local python -m tests.sandbox.debug_run <runner> <dir> [target]
"""

from __future__ import annotations

import base64
import json
import os
import sys
import uuid
from pathlib import Path

from testforge.core.config import Settings
from testforge.sandbox.protocol import RunRequest, SandboxLimits, WorkspaceFile
from testforge.sandbox.server import Runs


def main() -> None:
    runner, root = sys.argv[1], Path(sys.argv[2])
    targets = sys.argv[3:]
    files = [
        WorkspaceFile(
            path=str(p.relative_to(root)), content_b64=base64.b64encode(p.read_bytes()).decode()
        )
        for p in root.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    ]
    runs = Runs(Settings(sandbox_work_dir="/tmp/testforge-debug"))
    extra = os.environ.get("EXTRA_ARGS", "").split()
    if extra:
        r = runs.runners[runner]
        runs.runners[runner] = r.model_copy(update={"run": [*r.run, *extra]})
    job = uuid.uuid4().hex
    work = runs.root / job
    work.mkdir(parents=True)
    req = RunRequest(
        job_id=job,
        runner=runner,  # type: ignore[arg-type]
        files=files,
        targets=targets,
        coverage=os.environ.get("COVERAGE", "1") == "1",
        limits=SandboxLimits(cpu_s=30, wall_s=40),
    )
    result = runs.execute_sync(req, work)
    out = result.model_dump()
    out["coverage"] = (out["coverage"] or "")[:300]
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
