"""The runner registry (``runners.yaml``): how each test framework runs in the sandbox.

The API and the worker read it to know which framework a language uses; the sandbox reads
it to build commands. Both read the same file, so a framework the API offers is one the
sandbox runs (the CodeJudge ``languages.yaml`` pattern, for test runners).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

DEFAULT_FILE = Path(__file__).with_name("runners.yaml")
FRAMEWORK_FOR = {"python": "pytest", "javascript": "vitest", "typescript": "vitest"}


class Runner(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    name: str
    languages: list[str]
    run: list[str]
    coverage: list[str] = Field(default_factory=list)
    coverage_file: str
    coverage_tool: str
    env: list[str] = Field(default_factory=list)
    memory_mode: Literal["address", "rss"] = "address"
    memory_overhead_mb: int = Field(0, ge=0, le=2048)
    processes: int = Field(64, ge=1, le=4096)

    def command(self, *, coverage: bool, targets: list[str]) -> list[str]:
        return [*self.run, *(self.coverage if coverage else []), *targets]

    def environment(self, *, mem_mb: int) -> tuple[str, ...]:
        return tuple(e.format(mem=mem_mb) for e in self.env)


def load(path: str | Path | None = None) -> dict[str, Runner]:
    raw = yaml.safe_load(Path(path or DEFAULT_FILE).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not raw:
        raise ValueError("the runners file must map runner ids to their settings")
    return {rid: Runner(id=rid, **spec) for rid, spec in raw.items()}


@lru_cache
def registry(path: str | None = None) -> dict[str, Runner]:
    return load(path)


def framework_for(language: str) -> str:
    try:
        return FRAMEWORK_FOR[language]
    except KeyError:
        raise ValueError(f"no test runner for {language!r}") from None
