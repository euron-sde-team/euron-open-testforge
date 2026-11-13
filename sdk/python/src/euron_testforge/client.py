"""The TestForge clients. ``TestForge`` is synchronous; ``AsyncTestForge`` has the same
methods with ``await``. Both authenticate with a project API key (``tfk_...``), which also
selects the project, or with a session token plus ``project_id``.

Every method builds a ``Call`` (method, path, body, how to read the answer) once, and each
client only decides how to send it, so the two clients cannot drift apart.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from typing_extensions import Self

import httpx

from euron_testforge.errors import TestForgeError
from euron_testforge.models import GeneratedTest, Generation, Import, Run

DEFAULT_URL = "http://localhost:5630"


@dataclass(frozen=True)
class Call:
    method: str
    path: str
    json: Any = None
    params: dict[str, Any] = field(default_factory=dict)
    files: dict[str, Any] | None = None
    read: Callable[[Any], Any] = lambda body: body
    raw: bool = False


def _headers(api_key: str | None) -> dict[str, str]:
    h = {"user-agent": "euron-testforge-python/0.1.0", "x-tf-csrf": "1"}
    if api_key:
        h["authorization"] = f"Bearer {api_key}"
    return h


def _check(resp: httpx.Response, raw: bool) -> Any:
    if resp.status_code >= 400:
        try:
            err = resp.json().get("error", {})
        except ValueError:
            err = {}
        raise TestForgeError(
            resp.status_code,
            str(err.get("code", "http_error")),
            str(err.get("message", resp.text[:300])),
            err.get("details"),
        )
    if raw:
        return resp.content
    if resp.status_code == 204 or not resp.content:
        return None
    return resp.json()


class _Calls:
    """Every operation of the API the SDK covers, as ``Call`` objects."""

    def __init__(self, project_id: str) -> None:
        self.base = f"/api/v1/projects/{project_id}"

    def import_zip(self, path: str | Path, wait: float) -> Call:
        p = Path(path)
        return Call(
            "POST",
            f"{self.base}/imports/zip",
            params={"wait": wait},
            files={"file": (p.name, p.read_bytes(), "application/zip")},
            read=Import.of,
        )

    def import_github(self, repo: str | None, ref: str | None, wait: float) -> Call:
        return Call(
            "POST",
            f"{self.base}/imports/github",
            json={"repo": repo, "ref": ref},
            params={"wait": wait},
            read=Import.of,
        )

    def imports(self) -> Call:
        return Call("GET", f"{self.base}/imports", read=lambda b: [Import.of(x) for x in b])

    def analysis(self) -> Call:
        return Call("GET", f"{self.base}/analysis")

    def import_pull(self, number: int, repo: str | None, wait: float) -> Call:
        return Call(
            "POST",
            f"{self.base}/pulls",
            json={"number": number, "repo": repo},
            params={"wait": wait},
        )

    def import_spec(self, document: str) -> Call:
        return Call("POST", f"{self.base}/specs", json={"document": document})

    def generate(
        self,
        kinds: Sequence[str],
        unit_ids: Sequence[str] | None,
        pull_id: str | None,
        spec_id: str | None,
        instructions: str,
        wait: float,
    ) -> Call:
        body: dict[str, Any] = {"kinds": list(kinds), "instructions": instructions}
        if unit_ids is not None:
            body["unit_ids"] = list(unit_ids)
        if pull_id:
            body["pull_id"] = pull_id
        if spec_id:
            body["spec_id"] = spec_id
        return Call(
            "POST",
            f"{self.base}/tests/generate",
            json=body,
            params={"wait": wait},
            read=Generation.of,
        )

    def tests(self, status: str | None, generation_id: str | None) -> Call:
        params = {k: v for k, v in (("status", status), ("generation_id", generation_id)) if v}
        return Call(
            "GET",
            f"{self.base}/tests",
            params=params,
            read=lambda b: [GeneratedTest.of(x) for x in b],
        )

    def test_code(self, test_id: str) -> Call:
        return Call("GET", f"{self.base}/tests/{test_id}", read=lambda b: str(b["code"]))

    def review(self, ids: Sequence[str], status: str) -> Call:
        return Call(
            "POST",
            f"{self.base}/tests/review",
            json={"ids": list(ids), "status": status},
            read=lambda b: int(b["changed"]),
        )

    def run(self, kind: str, test_ids: Sequence[str] | None, wait: float) -> Call:
        body: dict[str, Any] = {"kind": kind}
        if test_ids is not None:
            body["test_ids"] = list(test_ids)
        return Call("POST", f"{self.base}/runs", json=body, params={"wait": wait}, read=Run.of)

    def get_run(self, run_id: str, wait: float) -> Call:
        return Call("GET", f"{self.base}/runs/{run_id}", params={"wait": wait}, read=Run.of)

    def runs(self) -> Call:
        return Call("GET", f"{self.base}/runs", read=lambda b: [Run.of(x) for x in b])

    def coverage(self) -> Call:
        return Call("GET", f"{self.base}/coverage")

    def report(self, scope: str, fmt: str, run_id: str | None) -> Call:
        return Call(
            "POST", f"{self.base}/reports", json={"scope": scope, "format": fmt, "run_id": run_id}
        )

    def download(self, report_id: str) -> Call:
        return Call("GET", f"{self.base}/reports/{report_id}/download", raw=True)


class _Base:
    def __init__(
        self,
        url: str | None = None,
        api_key: str | None = None,
        project_id: str | None = None,
    ) -> None:
        self.url = (url or os.environ.get("TESTFORGE_URL") or DEFAULT_URL).rstrip("/")
        self.api_key = api_key or os.environ.get("TESTFORGE_API_KEY")
        self.project_id = project_id or os.environ.get("TESTFORGE_PROJECT_ID")


class TestForge(_Base):
    """Synchronous client. ``with TestForge() as tf: tf.run()``."""

    __test__ = False

    def __init__(
        self,
        url: str | None = None,
        api_key: str | None = None,
        project_id: str | None = None,
        timeout: float = 900.0,
    ) -> None:
        super().__init__(url, api_key, project_id)
        self.http = httpx.Client(base_url=self.url, headers=_headers(self.api_key), timeout=timeout)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self.http.close()

    def _send(self, call: Call) -> Any:
        resp = self.http.request(
            call.method, call.path, json=call.json, params=call.params or None, files=call.files
        )
        return call.read(_check(resp, call.raw))

    def _calls(self) -> _Calls:
        if not self.project_id:
            self.project_id = str(_check(self.http.get("/api/v1/projects/current"), False)["id"])
        return _Calls(self.project_id)

    def import_zip(self, path: str | Path, wait: float = 120) -> Import:
        result: Import = self._send(self._calls().import_zip(path, wait))
        return result

    def import_github(
        self, repo: str | None = None, ref: str | None = None, wait: float = 120
    ) -> Import:
        result: Import = self._send(self._calls().import_github(repo, ref, wait))
        return result

    def imports(self) -> list[Import]:
        result: list[Import] = self._send(self._calls().imports())
        return result

    def analysis(self) -> dict[str, Any]:
        result: dict[str, Any] = self._send(self._calls().analysis())
        return result

    def import_pull(
        self, number: int, repo: str | None = None, wait: float = 120
    ) -> dict[str, Any]:
        result: dict[str, Any] = self._send(self._calls().import_pull(number, repo, wait))
        return result

    def import_spec(self, document: str) -> dict[str, Any]:
        result: dict[str, Any] = self._send(self._calls().import_spec(document))
        return result

    def generate(
        self,
        kinds: Sequence[str] = ("unit", "edge", "negative"),
        *,
        unit_ids: Sequence[str] | None = None,
        pull_id: str | None = None,
        spec_id: str | None = None,
        instructions: str = "",
        wait: float = 300,
    ) -> Generation:
        result: Generation = self._send(
            self._calls().generate(kinds, unit_ids, pull_id, spec_id, instructions, wait)
        )
        return result

    def tests(
        self, status: str | None = None, generation_id: str | None = None
    ) -> list[GeneratedTest]:
        result: list[GeneratedTest] = self._send(self._calls().tests(status, generation_id))
        return result

    def test_code(self, test_id: str) -> str:
        result: str = self._send(self._calls().test_code(test_id))
        return result

    def accept(self, ids: Sequence[str]) -> int:
        result: int = self._send(self._calls().review(ids, "accepted"))
        return result

    def discard(self, ids: Sequence[str]) -> int:
        result: int = self._send(self._calls().review(ids, "discarded"))
        return result

    def run(
        self, kind: str = "generated", test_ids: Sequence[str] | None = None, wait: float = 900
    ) -> Run:
        result: Run = self._send(self._calls().run(kind, test_ids, wait))
        return result

    def get_run(self, run_id: str, wait: float = 0) -> Run:
        result: Run = self._send(self._calls().get_run(run_id, wait))
        return result

    def runs(self) -> list[Run]:
        result: list[Run] = self._send(self._calls().runs())
        return result

    def coverage(self) -> dict[str, Any]:
        result: dict[str, Any] = self._send(self._calls().coverage())
        return result

    def report(self, scope: str = "run", fmt: str = "html", run_id: str | None = None) -> bytes:
        calls = self._calls()
        meta = self._send(calls.report(scope, fmt, run_id))
        data: bytes = self._send(calls.download(str(meta["id"])))
        return data


class AsyncTestForge(_Base):
    """Asynchronous client with the same methods as ``TestForge``."""

    __test__ = False

    def __init__(
        self,
        url: str | None = None,
        api_key: str | None = None,
        project_id: str | None = None,
        timeout: float = 900.0,
    ) -> None:
        super().__init__(url, api_key, project_id)
        self.http = httpx.AsyncClient(
            base_url=self.url, headers=_headers(self.api_key), timeout=timeout
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def close(self) -> None:
        await self.http.aclose()

    async def _send(self, call: Call) -> Any:
        resp = await self.http.request(
            call.method, call.path, json=call.json, params=call.params or None, files=call.files
        )
        return call.read(_check(resp, call.raw))

    async def _calls(self) -> _Calls:
        if not self.project_id:
            resp = await self.http.get("/api/v1/projects/current")
            self.project_id = str(_check(resp, False)["id"])
        return _Calls(self.project_id)

    async def import_zip(self, path: str | Path, wait: float = 120) -> Import:
        result: Import = await self._send((await self._calls()).import_zip(path, wait))
        return result

    async def import_github(
        self, repo: str | None = None, ref: str | None = None, wait: float = 120
    ) -> Import:
        result: Import = await self._send((await self._calls()).import_github(repo, ref, wait))
        return result

    async def analysis(self) -> dict[str, Any]:
        result: dict[str, Any] = await self._send((await self._calls()).analysis())
        return result

    async def generate(
        self,
        kinds: Sequence[str] = ("unit", "edge", "negative"),
        *,
        unit_ids: Sequence[str] | None = None,
        pull_id: str | None = None,
        spec_id: str | None = None,
        instructions: str = "",
        wait: float = 300,
    ) -> Generation:
        result: Generation = await self._send(
            (await self._calls()).generate(kinds, unit_ids, pull_id, spec_id, instructions, wait)
        )
        return result

    async def tests(
        self, status: str | None = None, generation_id: str | None = None
    ) -> list[GeneratedTest]:
        result: list[GeneratedTest] = await self._send(
            (await self._calls()).tests(status, generation_id)
        )
        return result

    async def accept(self, ids: Sequence[str]) -> int:
        result: int = await self._send((await self._calls()).review(ids, "accepted"))
        return result

    async def run(
        self, kind: str = "generated", test_ids: Sequence[str] | None = None, wait: float = 900
    ) -> Run:
        result: Run = await self._send((await self._calls()).run(kind, test_ids, wait))
        return result

    async def get_run(self, run_id: str, wait: float = 0) -> Run:
        result: Run = await self._send((await self._calls()).get_run(run_id, wait))
        return result

    async def coverage(self) -> dict[str, Any]:
        result: dict[str, Any] = await self._send((await self._calls()).coverage())
        return result
