"""Exported reports (CSV and HTML)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import Response

from testforge.core.deps import ContainerDep, SessionDep
from testforge.core.schemas import ApiModel
from testforge.projects.access import Viewer
from testforge.reports import service
from testforge.reports.models import Report

router = APIRouter(prefix="/api/v1/projects/{project_id}/reports", tags=["reports"])


class ReportCreate(ApiModel):
    scope: Literal["run", "project"] = "run"
    run_id: uuid.UUID | None = None
    format: Literal["csv", "html"] = "html"


class ReportOut(ApiModel):
    id: uuid.UUID
    scope: str
    run_id: uuid.UUID | None
    format: str
    title: str
    size_bytes: int
    created_at: datetime


@router.post(
    "",
    response_model=ReportOut,
    status_code=201,
    summary="Generate a report of a run or of the project's history",
)
async def create_report(
    body: ReportCreate, p: Viewer, session: SessionDep, container: ContainerDep
) -> Report:
    return await service.create(container, session, p, body.scope, body.format, body.run_id)


@router.get("", response_model=list[ReportOut], summary="Generated reports")
async def list_reports(p: Viewer, session: SessionDep) -> list[Report]:
    return list(await service.list_reports(session, p.project_id))


@router.get(
    "/{report_id}/download",
    summary="Download a report",
    response_class=Response,
    responses={200: {"content": {"text/html": {}, "text/csv": {}}}},
)
async def download(
    report_id: uuid.UUID, p: Viewer, session: SessionDep, container: ContainerDep
) -> Response:
    report = await service.get(session, p.project_id, report_id)
    data = await container.storage.get(report.object_key)
    name = f"testforge-{report.scope}-{str(report.id)[:8]}.{report.format}"
    return Response(
        data,
        media_type=service.CONTENT_TYPES[report.format],
        headers={
            "content-disposition": f'attachment; filename="{name}"',
            # A downloaded HTML report never runs script in the API's origin.
            "content-security-policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
            "cache-control": "private, max-age=300",
        },
    )
