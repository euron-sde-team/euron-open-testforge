"""Imports: create one (a ZIP upload or a GitHub repository), unpack it into a snapshot,
analyze it, and read its files and code units.

The API stores the upload and queues an import job; the worker does the slow part (the
GitHub download, unpacking, static analysis). Each step refuses unsafe input
(``archive.py``) and nothing is executed: analysis is static (``analysis/``).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from testforge.analysis import analyzer
from testforge.audit.service import Actor, audit
from testforge.core.container import Container
from testforge.core.errors import AppError, NotFoundError
from testforge.core.net import resolves_safely
from testforge.jobs import queue
from testforge.observability import metrics
from testforge.projects.access import Principal
from testforge.projects.models import Project
from testforge.sources import archive
from testforge.sources.github import GitHub, GitHubError, parse_repo
from testforge.sources.models import CodeUnit, SourceImport

log = logging.getLogger("testforge.sources")
INDEX_TTL_S = 600


def snapshot_key(project_id: uuid.UUID, import_id: uuid.UUID) -> str:
    return f"snapshots/{project_id}/{import_id}.zip"


async def github_client(container: Container, project: Project) -> GitHub:
    settings = container.settings
    if not await resolves_safely(
        settings.github_api_url, allow_private=settings.github_allow_private
    ):
        raise AppError(
            "The configured GitHub API address is not allowed (a private or metadata address)",
            code="github_forbidden_host",
        )
    token = None
    if project.github_token_sealed:
        token = await container.sealer.open(
            project.github_token_sealed, f"project:{project.id}:github_token"
        )
    return GitHub(container.http, settings.github_api_url, token, settings.github_timeout_s)


async def create_zip_import(
    container: Container, session: AsyncSession, p: Principal, filename: str, data: bytes
) -> SourceImport:
    if len(data) > container.settings.max_upload_bytes:
        raise AppError(
            f"The upload is larger than {container.settings.max_upload_bytes} bytes",
            code="upload_too_large",
        )
    if not data.startswith(b"PK"):
        raise AppError("Upload a ZIP archive of the project", code="not_a_zip")
    imp = SourceImport(
        project_id=p.project_id,
        kind="zip",
        label=(filename or "upload.zip")[:300],
        size_bytes=len(data),
        created_by=p.user_id,
    )
    session.add(imp)
    await session.flush()
    imp.upload_key = f"uploads/{p.project_id}/{imp.id}.zip"
    await container.storage.put(imp.upload_key, data, "application/zip")
    queue.enqueue(session, "import", p.project_id, imp.id)
    audit(
        session,
        p.actor,
        "import.created",
        "source_import",
        imp.id,
        kind="zip",
        label=imp.label,
        bytes=len(data),
        **p.audit_scope(),
    )
    await session.commit()
    await queue.notify(container)
    return imp


async def create_github_import(
    container: Container,
    session: AsyncSession,
    p: Principal,
    repo: str | None,
    ref: str | None,
    *,
    kind: str = "github",
    actor: Actor | None = None,
) -> SourceImport:
    project = p.project
    try:
        name = parse_repo(repo) if repo else project.github_repo
    except ValueError as exc:
        raise AppError(str(exc), code="invalid_repo") from None
    if not name:
        raise AppError(
            "Name the repository (owner/name), or set the project's GitHub repository first",
            code="repo_required",
        )
    if project.github_repo is None:
        project.github_repo = name
    imp = SourceImport(
        project_id=p.project_id,
        kind=kind,
        label=f"{name}@{ref}" if ref else name,
        repo=name,
        ref=ref,
        created_by=p.user_id,
    )
    session.add(imp)
    await session.flush()
    queue.enqueue(session, "import", p.project_id, imp.id)
    audit(
        session,
        actor or p.actor,
        "import.created",
        "source_import",
        imp.id,
        kind=kind,
        repo=name,
        ref=ref,
        **p.audit_scope(),
    )
    await session.commit()
    await queue.notify(container)
    return imp


async def list_imports(
    session: AsyncSession, project_id: uuid.UUID, limit: int = 50
) -> Sequence[SourceImport]:
    return (
        await session.scalars(
            select(SourceImport)
            .where(SourceImport.project_id == project_id)
            .order_by(SourceImport.created_at.desc())
            .limit(limit)
        )
    ).all()


async def get_import(
    session: AsyncSession, project_id: uuid.UUID, import_id: uuid.UUID
) -> SourceImport:
    imp = await session.scalar(
        select(SourceImport).where(
            SourceImport.id == import_id, SourceImport.project_id == project_id
        )
    )
    if imp is None:
        raise NotFoundError("Import not found")
    return imp


async def current_import(session: AsyncSession, project: Project) -> SourceImport:
    """The import generation and runs use: the project's current one, else the latest
    ready import."""
    if project.current_import_id:
        imp = await session.get(SourceImport, project.current_import_id)
        if imp is not None and imp.status == "ready":
            return imp
    imp = await session.scalar(
        select(SourceImport)
        .where(SourceImport.project_id == project.id, SourceImport.status == "ready")
        .order_by(SourceImport.created_at.desc())
        .limit(1)
    )
    if imp is None:
        raise AppError(
            "Import the project's source first (a GitHub repository or a ZIP upload)",
            code="no_import",
        )
    return imp


async def units(
    session: AsyncSession,
    import_id: uuid.UUID,
    *,
    kind: str | None = None,
    untested: bool = False,
    file: str | None = None,
    ids: list[uuid.UUID] | None = None,
) -> Sequence[CodeUnit]:
    stmt = select(CodeUnit).where(CodeUnit.import_id == import_id)
    if kind:
        stmt = stmt.where(CodeUnit.kind == kind)
    if file:
        stmt = stmt.where(CodeUnit.file == file)
    if ids is not None:
        stmt = stmt.where(CodeUnit.id.in_(ids))
    if untested:
        stmt = stmt.where(
            CodeUnit.exported.is_(True),
            CodeUnit.kind != "class",
            CodeUnit.referenced_by_tests.is_(False),
            (CodeUnit.covered_percent.is_(None)) | (CodeUnit.covered_percent == 0),
        )
    return (await session.scalars(stmt.order_by(CodeUnit.file, CodeUnit.start_line))).all()


# ── Snapshot files ───────────────────────────────────────────────────────────────────


async def snapshot_files(container: Container, imp: SourceImport) -> dict[str, str]:
    if not imp.snapshot_key:
        raise AppError("This import has no snapshot yet", code="import_not_ready")
    data = await container.storage.get(imp.snapshot_key)
    return await asyncio.to_thread(archive.read_snapshot, data)


async def file_index(container: Container, imp: SourceImport) -> list[dict[str, object]]:
    """Paths and sizes of the snapshot, cached (a snapshot never changes)."""
    key = f"tf:index:{imp.id}"
    try:
        cached = await container.kv.get(key)
    except Exception:
        metrics.DEPENDENCY_ERRORS.labels("redis", "get").inc()
        cached = None
    if cached:
        value: list[dict[str, object]] = json.loads(cached)
        return value
    files = await snapshot_files(container, imp)
    index: list[dict[str, object]] = [
        {"path": p, "bytes": len(t.encode()), "language": analyzer.language_of(p)}
        for p, t in sorted(files.items())
    ]
    try:
        await container.kv.set(key, json.dumps(index).encode(), INDEX_TTL_S)
    except Exception:
        metrics.DEPENDENCY_ERRORS.labels("redis", "set").inc()
    return index


# ── The import job (worker) ──────────────────────────────────────────────────────────


async def _fetch(
    container: Container, session: AsyncSession, imp: SourceImport
) -> archive.Snapshot:
    s = container.settings
    limits = {
        "max_files": s.max_snapshot_files,
        "max_bytes": s.max_snapshot_bytes,
        "max_file_bytes": s.max_file_bytes,
    }
    if imp.kind == "zip":
        if not imp.upload_key:
            raise archive.ArchiveError("The upload is missing")
        data = await container.storage.get(imp.upload_key)
        return await asyncio.to_thread(archive.from_zip, data, **limits)
    project = await session.get(Project, imp.project_id)
    assert project is not None
    gh = await github_client(container, project)
    repo = imp.repo or ""
    ref = imp.ref or await gh.default_branch(repo)
    imp.ref = ref
    sha = imp.commit_sha or await gh.commit_sha(repo, ref)
    imp.commit_sha = sha
    data = await gh.tarball(repo, sha, s.max_upload_bytes * 4)
    return await asyncio.to_thread(archive.from_tarball, data, **limits)


async def process(container: Container, session: AsyncSession, imp: SourceImport) -> None:
    """Fetch, unpack and analyze one import (the worker's import job). Failures are
    recorded on the import with a reason a person can act on."""
    imp.status = "analyzing"
    await session.commit()
    try:
        snap = await _fetch(container, session, imp)
    except (archive.ArchiveError, GitHubError, AppError) as exc:
        imp.status = "failed"
        imp.error = getattr(exc, "message", None) or str(exc)
        await session.commit()
        return
    key = snapshot_key(imp.project_id, imp.id)
    await container.storage.put(key, await asyncio.to_thread(snap.to_zip), "application/zip")
    if imp.upload_key:
        await container.storage.delete(imp.upload_key)
        imp.upload_key = None
    imp.snapshot_key = key
    imp.size_bytes = snap.size
    imp.file_count = len(snap.files)
    await analyze(session, imp, snap.files, snap.skipped)
    project = await session.get(Project, imp.project_id)
    if project is not None and imp.kind != "pull_request":
        project.current_import_id = imp.id
    audit(
        session,
        Actor(None, "worker", "system"),
        "import.ready",
        "source_import",
        imp.id,
        files=imp.file_count,
        units=imp.summary.get("units", 0),
        languages=imp.languages,
        commit=imp.commit_sha,
        project_id=imp.project_id,
        org_id=project.org_id if project else None,
    )
    await session.commit()


async def analyze(
    session: AsyncSession,
    imp: SourceImport,
    files: dict[str, str],
    skipped: list[str] | None = None,
) -> None:
    """Static analysis of a snapshot into code units and the import summary. Runs in a
    thread (it is CPU work) and replaces the import's previous units."""
    started = time.perf_counter()
    result, referenced = await asyncio.to_thread(analyzer.analyze, files)
    elapsed = time.perf_counter() - started
    metrics.ANALYSIS_SECONDS.observe(elapsed)
    await session.execute(delete(CodeUnit).where(CodeUnit.import_id == imp.id))
    session.add_all(
        CodeUnit(
            import_id=imp.id,
            project_id=imp.project_id,
            kind=u.kind,
            language=u.language,
            name=u.name[:200],
            qualname=u.qualname[:400],
            file=u.file[:500],
            module=u.module[:500],
            start_line=u.start_line,
            end_line=u.end_line,
            signature=u.signature[:4000],
            docstring=u.docstring[:8000],
            source=u.source,
            details=u.details(),
            exported=u.exported,
            is_async=u.is_async,
            statement_lines=len(u.statement_lines),
            referenced_by_tests=u.qualname in referenced,
        )
        for u in result.units
    )
    summary = result.summary()
    summary["skipped"] = (summary.get("skipped") or []) + (skipped or [])[:200]
    summary["untested"] = sum(
        1 for u in result.units if u.exported and u.kind != "class" and u.qualname not in referenced
    )
    imp.languages = result.languages
    imp.frameworks = result.frameworks
    imp.test_frameworks = result.test_frameworks
    imp.summary = summary
    imp.analysis_ms = round(elapsed * 1000)
    imp.analyzed_at = datetime.now(UTC)
    imp.status = "ready"
    imp.error = None


async def count_units(session: AsyncSession, import_id: uuid.UUID) -> int:
    return int(
        await session.scalar(select(func.count()).where(CodeUnit.import_id == import_id)) or 0
    )
