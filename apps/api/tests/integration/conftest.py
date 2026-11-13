"""Integration harness: the real API served over HTTP from a background thread and the real
worker in another, against real Postgres, Redis, the mock services (model providers and a
GitHub API serving the demo repositories) and the real sandbox service, which runs every
test in nsjail exactly as in production.

    make test-integration      (starts Postgres, Redis, the mock services and the sandbox)

Isolation: every run uses its own database (``TEST_DATABASE_URL``) and Redis DB index
(``TEST_REDIS_URL``). The suite drops and recreates the database, so it refuses any
database whose name does not contain "test" and any non-local host unless
ALLOW_REMOTE_TEST_DB=true.
"""

from __future__ import annotations

import asyncio
import io
import os
import socket
import threading
import time
import zipfile
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import pytest
import redis.asyncio as aioredis
import uvicorn
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from testforge.core.config import Settings

ROOT = Path(__file__).resolve().parents[4]
DEMO = ROOT / "apps" / "api" / "src" / "testforge" / "demo" / "projects"
ADMIN = {"email": "admin@example.test", "password": "Admin-Pass-123"}
CSRF = {"x-tf-csrf": "1"}


def _compose_env() -> dict[str, str]:
    """deploy/compose/.env (written by make env): the demo servers' admin password."""
    path = ROOT / "deploy" / "compose" / ".env"
    out: dict[str, str] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            key, sep, value = line.partition("=")
            if sep and not key.startswith("#"):
                out[key.strip()] = value.strip()
    return out


_ENV = _compose_env()
TEST_DB = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://testforge:testforge@localhost:"
    f"{_ENV.get('TESTFORGE_PG_PORT', '5642')}/testforge_test",
)
TEST_REDIS = os.environ.get(
    "TEST_REDIS_URL", f"redis://localhost:{_ENV.get('TESTFORGE_REDIS_PORT', '5679')}/15"
)
SANDBOX_URL = os.environ.get(
    "TEST_SANDBOX_URL", f"http://127.0.0.1:{_ENV.get('TESTFORGE_SANDBOX_PORT', '5635')}"
)
SANDBOX_SECRET = os.environ.get("TEST_SANDBOX_SECRET", _ENV.get("SANDBOX_SECRET", ""))


def _guard(url: str) -> None:
    parsed = urlparse(url.replace("+asyncpg", ""))
    if "test" not in (parsed.path or ""):
        raise RuntimeError(f"refusing {parsed.path!r}: the test database name must contain 'test'")
    if (
        parsed.hostname not in ("localhost", "127.0.0.1", "postgres")
        and os.environ.get("ALLOW_REMOTE_TEST_DB") != "true"
    ):
        raise RuntimeError("refusing a non-local test database (set ALLOW_REMOTE_TEST_DB=true)")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class Served:
    """An ASGI app (or import string) served by uvicorn on a thread, with its own loop."""

    def __init__(self, app: Any, port: int | None = None) -> None:
        self.port = port or free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        config = uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="warning")
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def start(self, health: str = "/healthz") -> Served:
        self.thread.start()
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                if httpx.get(self.url + health, timeout=1).status_code < 500:
                    return self
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        raise RuntimeError(f"server on {self.url} did not start")

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=15)


class WorkerThread:
    """The real worker (``testforge.worker.serve``) on its own thread and loop."""

    def __init__(self, settings: Settings, run_tasks: bool = False) -> None:
        self.settings = settings
        self.run_tasks = run_tasks
        self.loop = asyncio.new_event_loop()
        self.stop_event: asyncio.Event | None = None
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.ready = threading.Event()

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._main())

    async def _main(self) -> None:
        from testforge.core.container import Container
        from testforge.worker import import_task_modules, serve

        import_task_modules()
        container = Container.build(self.settings)
        self.stop_event = asyncio.Event()
        self.ready.set()
        try:
            await serve(container, self.stop_event, self.settings, run_tasks=self.run_tasks)
        finally:
            await container.close()

    def start(self) -> WorkerThread:
        self.thread.start()
        self.ready.wait(10)
        return self

    def stop(self) -> None:
        if self.stop_event is not None:
            self.loop.call_soon_threadsafe(self.stop_event.set)
        self.thread.join(timeout=60)


@pytest.fixture(scope="session")
def mock_ai() -> Iterator[str]:
    served = Served("mockai.app:app").start()
    yield served.url
    served.stop()


@pytest.fixture(scope="session")
async def database() -> AsyncIterator[str]:
    """A fresh database built by the migrations (so they are tested on every run)."""
    _guard(TEST_DB)
    admin_url = TEST_DB.rsplit("/", 1)[0] + "/postgres"
    name = TEST_DB.rsplit("/", 1)[1]
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        await conn.execute(text(f'CREATE DATABASE "{name}"'))
    await engine.dispose()
    from testforge.migrations.runner import upgrade

    await asyncio.to_thread(upgrade, TEST_DB)
    yield TEST_DB


def demo_zip(name: str, *, extra: dict[str, str] | None = None) -> bytes:
    """A demo project as the ZIP a developer would upload."""
    buf = io.BytesIO()
    root = DEMO / name
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(root.rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts:
                zf.writestr(f"{name}/{p.relative_to(root)}", p.read_bytes())
        for path, text in (extra or {}).items():
            zf.writestr(f"{name}/{path}", text)
    return buf.getvalue()


@pytest.fixture(scope="session")
def sandbox() -> str:
    """The real sandbox service (make test-integration starts it)."""
    if not SANDBOX_SECRET:
        raise RuntimeError("no sandbox secret: run make env (or set TEST_SANDBOX_SECRET)")
    try:
        ok = httpx.get(f"{SANDBOX_URL}/healthz", timeout=5).json().get("nsjail")
    except httpx.HTTPError as exc:
        raise RuntimeError(
            f"the sandbox service is not reachable on {SANDBOX_URL}: run make test-integration"
        ) from exc
    if not ok:
        raise RuntimeError("the sandbox service has no nsjail")
    return SANDBOX_URL


def make_settings(database: str, tmp_path: Path, mock_ai: str, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "environment": "test",
        "database_url": database,
        "redis_url": TEST_REDIS,
        "session_secret": "test-only-session-secret-with-32-plus-bytes",
        "api_key_pepper": "test-only-api-key-pepper-with-32-plus-bytes",
        "local_master_key": "test-only-master-key-with-32-plus-bytes-ok",
        "local_storage_dir": str(tmp_path / "objects"),
        "work_dir": str(tmp_path / "work"),
        "public_url": "http://localhost:5610",
        "mail_backend": "log",
        "sandbox_url": SANDBOX_URL,
        "sandbox_secret": SANDBOX_SECRET,
        "github_api_url": f"{mock_ai}/github",
        "github_allow_private": True,
        "webhook_allow_private": True,
        "generate_rpm": 100_000,
        "run_rpm": 100_000,
        "run_wall_s": 90,
        "lease_s": 30.0,
        "worker_poll_interval_s": 0.2,
        "task_interval_s": 0.5,
        "worker_metrics_port": 0,
        "worker_concurrency": 4,
        "key_mode": os.environ.get("TEST_KEY_MODE", "local"),
        "storage": os.environ.get("TEST_STORAGE", "local"),
        "aws_endpoint_url": os.environ.get("TEST_AWS_ENDPOINT"),
        "s3_force_path_style": True,
        "kms_key_id": os.environ.get("TEST_KMS_KEY_ID", "alias/testforge-local"),
        "objects_bucket": os.environ.get("TEST_OBJECTS_BUCKET", "testforge-local-objects"),
    }
    values.update(overrides)
    return Settings(**values)


async def reset(database: str) -> None:
    """Empty every table and the Redis DB between tests."""
    engine = create_async_engine(database)
    async with engine.begin() as conn:
        # A session a previous test left inside a transaction would block TRUNCATE.
        await conn.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = "
                "current_database() AND pid <> pg_backend_pid() AND state LIKE 'idle in transaction%'"
            )
        )
    async with engine.begin() as conn:
        tables = (
            await conn.execute(
                text(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                    "AND tablename NOT IN ('alembic_version', 'audit_log')"
                )
            )
        ).scalars()
        names = ", ".join(f'"{t}"' for t in tables)
        if names:
            await conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    await engine.dispose()
    r = aioredis.Redis.from_url(TEST_REDIS)
    await r.flushdb()
    await r.aclose()


async def bootstrap_admin(database: str) -> None:
    from testforge.audit.service import Actor
    from testforge.core.db import Database
    from testforge.core.security import hash_password
    from testforge.orgs import service as orgs
    from testforge.users.models import User

    db = Database(database, pool_size=1, max_overflow=0)
    async with db.sessionmaker() as session:
        user = User(
            email=ADMIN["email"],
            name="Admin",
            role="admin",
            password_hash=hash_password(ADMIN["password"]),
        )
        session.add(user)
        await session.flush()
        await orgs.create_for(session, user, "Acme", Actor(user.id, user.email, "admin"))
        await session.commit()
    await db.dispose()


async def login(base_url: str, creds: dict[str, str] = ADMIN) -> httpx.AsyncClient:
    client = httpx.AsyncClient(base_url=base_url, timeout=180, headers=CSRF)
    resp = await client.post("/api/v1/auth/login", json=creds)
    assert resp.status_code == 200, resp.text
    client.headers["authorization"] = f"Bearer {resp.json()['session_token']}"
    return client


@dataclass
class Stack:
    """The running API and worker, a signed-in admin, the current project, and helpers."""

    api_url: str
    settings: Settings
    client: httpx.AsyncClient
    mock_ai_url: str
    worker: WorkerThread | None
    org_id: str
    project_id: str = ""

    async def ok(
        self,
        method: str,
        path: str,
        json: Any = None,
        status: int | None = None,
        client: httpx.AsyncClient | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        c = client or self.client
        resp = await c.request(method, path, json=json, params=params)
        expected = status or (201 if method == "POST" and resp.status_code == 201 else 200)
        assert resp.status_code == expected, f"{method} {path}: {resp.status_code} {resp.text}"
        if not resp.content:
            return None
        if "json" not in resp.headers.get("content-type", ""):
            return resp.content
        return resp.json()

    def p(self, path: str = "") -> str:
        return f"/api/v1/projects/{self.project_id}{path}"

    async def project(self, name: str = "Shop") -> dict[str, Any]:
        out = dict(
            await self.ok(
                "POST", "/api/v1/projects", {"org_id": self.org_id, "name": name}, status=201
            )
        )
        self.project_id = out["id"]
        return out

    async def provider(
        self,
        name: str = "mock",
        kind: str = "mock",
        client: httpx.AsyncClient | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        base = {
            "mock": None,
            "openai_compatible": f"{self.mock_ai_url}/v1",
            "openai": f"{self.mock_ai_url}/v1",
            "anthropic": f"{self.mock_ai_url}/anthropic",
            "gemini": f"{self.mock_ai_url}/gemini",
            "ollama": f"{self.mock_ai_url}/ollama",
        }[kind]
        body: dict[str, Any] = {"name": name, "kind": kind}
        if base:
            body |= {"base_url": base, "api_key": f"sk-{name}-secret", "model": "mock-tests-small"}
        body |= extra
        return dict(await self.ok("POST", self.p("/providers"), body, status=201, client=client))

    async def import_zip(
        self, name: str = "python-shop", *, extra: dict[str, str] | None = None, wait: float = 60,
        client: httpx.AsyncClient | None = None,
    ) -> dict[str, Any]:
        c = client or self.client
        resp = await c.post(
            self.p("/imports/zip"),
            params={"wait": wait},
            files={"file": (f"{name}.zip", demo_zip(name, extra=extra), "application/zip")},
        )
        assert resp.status_code == 202, resp.text
        return dict(resp.json())

    async def import_github(self, repo: str, ref: str | None = None, wait: float = 60) -> dict[str, Any]:
        return dict(
            await self.ok(
                "POST", self.p("/imports/github"), {"repo": repo, "ref": ref},
                status=202, params={"wait": wait},
            )
        )

    async def generate(
        self, *, wait: float = 120, client: httpx.AsyncClient | None = None,
        status: int = 202, **body: Any,
    ) -> dict[str, Any]:
        return dict(
            await self.ok("POST", self.p("/tests/generate"), body, status=status, params={"wait": wait}, client=client)
        )

    async def tests(self, **params: Any) -> list[dict[str, Any]]:
        return list(await self.ok("GET", self.p("/tests"), params=params))

    async def accept_all(self, generation_id: str) -> list[dict[str, Any]]:
        tests = await self.tests(generation_id=generation_id)
        if tests:
            await self.ok("POST", self.p("/tests/review"), {"ids": [t["id"] for t in tests], "status": "accepted"})
        return tests

    async def run(
        self, *, wait: float = 240, status: int = 202, client: httpx.AsyncClient | None = None, **body: Any
    ) -> dict[str, Any]:
        return dict(await self.ok("POST", self.p("/runs"), body, status=status, params={"wait": wait}, client=client))

    async def audit(self, **params: Any) -> list[dict[str, Any]]:
        return list((await self.ok("GET", self.p("/audit-logs"), params=params))["items"])

    async def user_in_org(
        self, role: str = "member", email: str | None = None
    ) -> httpx.AsyncClient:
        email = email or f"{role}-{time.monotonic_ns()}@example.test"
        password = "User-Pass-123"
        await self.ok(
            "POST",
            f"/api/v1/orgs/{self.org_id}/members",
            {"email": email, "role": role, "name": "Test User", "password": password},
            status=201,
        )
        return await login(self.api_url, {"email": email, "password": password})

    async def member(self, role: str) -> tuple[httpx.AsyncClient, str]:
        """A person in the organization with ``role`` in the current project."""
        client = await self.user_in_org("member")
        me = (await client.get("/api/v1/auth/me")).json()
        await self.ok(
            "POST",
            self.p("/members"),
            {"email": me["email"], "role": role},
            status=201,
        )
        return client, str(me["id"])


@pytest.fixture
def settings_overrides() -> dict[str, Any]:
    """Tests override this to change the API's and the worker's settings."""
    return {}


@pytest.fixture
def run_worker() -> bool:
    """Tests that drive the queue by hand override this to False."""
    return True


@pytest.fixture
async def stack(
    database: str,
    tmp_path: Path,
    mock_ai: str,
    sandbox: str,
    settings_overrides: dict[str, Any],
    run_worker: bool,
) -> AsyncIterator[Stack]:
    from testforge.main import create_app

    await reset(database)
    await bootstrap_admin(database)
    settings = make_settings(database, tmp_path, mock_ai, **settings_overrides)
    served = Served(create_app(settings)).start()
    worker = WorkerThread(settings).start() if run_worker else None
    client = await login(served.url)
    org_id = (await client.get("/api/v1/orgs")).json()[0]["id"]
    async with httpx.AsyncClient() as http:
        await http.post(f"{mock_ai}/_mock/reset")
    stack = Stack(served.url, settings, client, mock_ai, worker, org_id)
    try:
        yield stack
    finally:
        await client.aclose()
        # A test may have replaced or started the worker: stop whichever is running now.
        for w in {id(x): x for x in (worker, stack.worker) if x is not None}.values():
            w.stop()
        served.stop()


@pytest.fixture
async def ready(stack: Stack) -> Stack:
    """A stack with a project and the built-in mock provider as its default."""
    await stack.project()
    await stack.provider()
    return stack


@pytest.fixture
async def shop(ready: Stack) -> Stack:
    """A ready stack with the demo Python project imported from a ZIP and analyzed."""
    imp = await ready.import_zip("python-shop")
    assert imp["status"] == "ready", imp
    return ready
