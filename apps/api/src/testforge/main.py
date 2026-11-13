"""API application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from testforge import __version__
from testforge.audit.router import router as audit_router
from testforge.auth.router import router as auth_router
from testforge.bugs.router import router as bugs_router
from testforge.core.config import Settings, get_settings
from testforge.core.container import Container
from testforge.core.db import import_all_models
from testforge.core.errors import install_error_handlers
from testforge.core.logs import configure_logging
from testforge.core.middleware import BodySizeLimitMiddleware, RequestContextMiddleware
from testforge.core.tracing import configure_tracing
from testforge.coverage.router import router as coverage_router
from testforge.generation.router import router as tests_router
from testforge.instance.router import router as instance_router
from testforge.orgs.router import router as orgs_router
from testforge.overview.router import router as overview_router
from testforge.projects.router import router as projects_router
from testforge.providers.router import router as providers_router
from testforge.pulls.router import router as pulls_router
from testforge.reports.router import router as reports_router
from testforge.runs.router import router as runs_router
from testforge.sources.router import router as sources_router
from testforge.specs.router import router as specs_router
from testforge.system.router import router as system_router
from testforge.usage.router import router as usage_router
from testforge.users.router import router as users_router
from testforge.webhooks.router import router as webhooks_router

DESCRIPTION = """
API of a self-hosted platform that writes and runs tests for your own code. Import a GitHub
repository or a ZIP of a Python, JavaScript or TypeScript project; TestForge analyzes it
statically, generates unit, edge-case, negative and API tests whose assertions come from
the real code, refuses any generated test without a meaningful assertion, and runs tests in
an unprivileged sandbox with no network, no credentials and a CPU, memory, output and wall
clock budget. Failures are explained from the values the same run captured; coverage is
read from coverage.py and Istanbul, never estimated.

* People sign in with `POST /api/v1/auth/login` and send the session token as
  `Authorization: Bearer <token>` (the dashboard uses an HttpOnly cookie instead).
* Applications, CI, the SDK and the CLI use a project API key: `Authorization: Bearer
  tfk_...` or `X-API-Key: tfk_...`. Scopes: `read`, `generate`, `execute`, `manage`.
* The usual path: `POST .../imports/github` (or `.../imports/zip`), `POST .../tests/generate`,
  `PATCH .../tests/{id}` to accept, `POST .../runs`, then `GET .../runs/{id}`. Every long call
  takes `?wait=<seconds>` to return when the work is done.
"""


def create_app(settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    settings = settings or get_settings()
    import_all_models()
    configure_logging(settings.log_level)
    configure_tracing(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.container = container or Container.build(settings)
        try:
            yield
        finally:
            if container is None:
                await app.state.container.close()

    app = FastAPI(
        title="Euron Open TestForge",
        version=__version__,
        description=DESCRIPTION,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
        openapi_url="/openapi.json",
        separate_input_output_schemas=False,
    )
    install_error_handlers(app)
    for router in (
        auth_router,
        users_router,
        instance_router,
        orgs_router,
        projects_router,
        providers_router,
        sources_router,
        specs_router,
        pulls_router,
        tests_router,
        runs_router,
        coverage_router,
        bugs_router,
        reports_router,
        webhooks_router,
        overview_router,
        usage_router,
        audit_router,
        system_router,
    ):
        app.include_router(router)

    app.add_middleware(GZipMiddleware, minimum_size=2048)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "authorization",
            "content-type",
            "x-tf-csrf",
            "x-api-key",
            "x-project-id",
            "x-request-id",
        ],
        expose_headers=["x-request-id", "retry-after", "content-disposition"],
        max_age=600,
    )
    app.add_middleware(BodySizeLimitMiddleware, settings=settings)
    app.add_middleware(RequestContextMiddleware)
    return app
