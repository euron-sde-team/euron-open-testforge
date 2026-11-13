"""Imports (a GitHub repository or a ZIP upload), their analysis, code units and files."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, File, Query, UploadFile

from testforge.analysis.analyzer import language_of
from testforge.core.deps import ContainerDep, SessionDep
from testforge.core.errors import AppError, NotFoundError
from testforge.coverage.models import CoverageReport
from testforge.jobs import queue
from testforge.projects.access import Editor, Viewer
from testforge.sources import service
from testforge.sources.models import SourceImport
from testforge.sources.schemas import (
    AnalysisOut,
    FileContent,
    FileOut,
    GitHubImport,
    ImportOut,
    UnitDetail,
    UnitOut,
)

router = APIRouter(prefix="/api/v1/projects/{project_id}", tags=["imports"])
WAIT_MAX_S = 120.0


async def _waited(
    container: ContainerDep, session: SessionDep, imp: SourceImport, wait: float
) -> SourceImport:
    if wait > 0:
        await queue.wait_for(container, imp.id, min(wait, WAIT_MAX_S))
        await session.refresh(imp)
    return imp


@router.post(
    "/imports/zip",
    response_model=ImportOut,
    status_code=202,
    summary="Import a project from a ZIP upload (Python, JavaScript or TypeScript)",
    description="The archive is unpacked defensively (no links, no paths outside the project, "
    "size and file caps) and analyzed statically; nothing in it runs until a test run, in the "
    "sandbox. Pass `wait` (seconds) to return once the analysis is done.",
)
async def import_zip(
    p: Editor,
    session: SessionDep,
    container: ContainerDep,
    file: UploadFile = File(...),
    wait: float = Query(0, ge=0, le=WAIT_MAX_S),
) -> SourceImport:
    data = await file.read(container.settings.max_upload_bytes + 1)
    imp = await service.create_zip_import(
        container, session, p, file.filename or "upload.zip", data
    )
    return await _waited(container, session, imp, wait)


@router.post(
    "/imports/github",
    response_model=ImportOut,
    status_code=202,
    summary="Import a GitHub repository at a branch, tag or commit",
    description="The repository arrives as GitHub's archive of one commit: nothing is cloned and "
    "no hook runs. A private repository needs the project's GitHub token (Settings).",
)
async def import_github(
    body: GitHubImport,
    p: Editor,
    session: SessionDep,
    container: ContainerDep,
    wait: float = Query(0, ge=0, le=WAIT_MAX_S),
) -> SourceImport:
    imp = await service.create_github_import(container, session, p, body.repo, body.ref)
    return await _waited(container, session, imp, wait)


@router.get("/imports", response_model=list[ImportOut], summary="Imports, newest first")
async def list_imports(p: Viewer, session: SessionDep) -> list[SourceImport]:
    return list(await service.list_imports(session, p.project_id))


@router.get(
    "/imports/{import_id}", response_model=ImportOut, summary="One import and its analysis summary"
)
async def get_import(
    import_id: uuid.UUID,
    p: Viewer,
    session: SessionDep,
    container: ContainerDep,
    wait: float = Query(0, ge=0, le=WAIT_MAX_S),
) -> SourceImport:
    imp = await service.get_import(session, p.project_id, import_id)
    if imp.status in ("pending", "analyzing"):
        imp = await _waited(container, session, imp, wait)
    return imp


@router.post(
    "/imports/{import_id}/analyze",
    response_model=ImportOut,
    summary="Analyze an import again (after an upgrade of TestForge's analyzers)",
)
async def reanalyze(
    import_id: uuid.UUID, p: Editor, session: SessionDep, container: ContainerDep
) -> SourceImport:
    imp = await service.get_import(session, p.project_id, import_id)
    files = await service.snapshot_files(container, imp)
    await service.analyze(session, imp, files, (imp.summary or {}).get("skipped"))
    await session.commit()
    return imp


@router.get(
    "/analysis",
    response_model=AnalysisOut,
    summary="The current source analysis: languages, frameworks, units and untested code",
)
async def analysis(p: Viewer, session: SessionDep) -> AnalysisOut:
    try:
        imp = await service.current_import(session, p.project)
    except AppError:
        return AnalysisOut()
    untested = await service.units(session, imp.id, untested=True)
    summary = imp.summary or {}
    return AnalysisOut.model_validate(
        {
            "import": ImportOut.model_validate(imp),
            "units": summary.get("units", 0),
            "by_kind": summary.get("by_kind", {}),
            "untested": len(untested),
            "untested_units": [UnitOut.model_validate(u) for u in untested[:100]],
        }
    )


@router.get(
    "/imports/{import_id}/units",
    response_model=list[UnitOut],
    summary="Functions, methods, classes and routes",
)
async def list_units(
    import_id: uuid.UUID,
    p: Viewer,
    session: SessionDep,
    kind: str | None = Query(None, pattern=r"^(function|method|class|route)$"),
    untested: bool = False,
    file: str | None = Query(None, max_length=500),
) -> list[UnitOut]:
    await service.get_import(session, p.project_id, import_id)
    rows = await service.units(session, import_id, kind=kind, untested=untested, file=file)
    return [UnitOut.model_validate(u) for u in rows]


@router.get(
    "/imports/{import_id}/units/{unit_id}",
    response_model=UnitDetail,
    summary="One code unit with its source",
)
async def get_unit(
    import_id: uuid.UUID, unit_id: uuid.UUID, p: Viewer, session: SessionDep
) -> UnitDetail:
    await service.get_import(session, p.project_id, import_id)
    rows = await service.units(session, import_id, ids=[unit_id])
    if not rows:
        raise NotFoundError("Code unit not found")
    return UnitDetail.model_validate(rows[0])


@router.get(
    "/imports/{import_id}/files", response_model=list[FileOut], summary="Files in the snapshot"
)
async def list_files(
    import_id: uuid.UUID, p: Viewer, session: SessionDep, container: ContainerDep
) -> list[FileOut]:
    imp = await service.get_import(session, p.project_id, import_id)
    return [FileOut.model_validate(f) for f in await service.file_index(container, imp)]


@router.get(
    "/imports/{import_id}/file",
    response_model=FileContent,
    summary="One file, its units and its coverage",
)
async def get_file(
    import_id: uuid.UUID,
    p: Viewer,
    session: SessionDep,
    container: ContainerDep,
    path: str = Query(..., max_length=500),
) -> FileContent:
    imp = await service.get_import(session, p.project_id, import_id)
    files = await service.snapshot_files(container, imp)
    if path not in files:
        raise NotFoundError("No such file in this import")
    units = await service.units(session, imp.id, file=path)
    from sqlalchemy import select

    latest = await session.scalar(
        select(CoverageReport)
        .where(CoverageReport.import_id == imp.id)
        .order_by(CoverageReport.created_at.desc())
        .limit(1)
    )
    covered: list[int] = []
    missing: list[int] = []
    if latest is not None:
        entry = next((f for f in latest.files if f.get("path") == path), None)
        if entry is not None:
            miss = {n for a, b in entry.get("missing", []) for n in range(a, b + 1)}
            missing = sorted(miss)
            stmts = {n for u in units for n in (u.details or {}).get("statement_lines", [])}
            covered = sorted(stmts - miss)
    return FileContent(
        path=path,
        content=files[path],
        language=language_of(path),
        units=[UnitOut.model_validate(u) for u in units],
        covered_lines=covered,
        missing_lines=missing,
    )
