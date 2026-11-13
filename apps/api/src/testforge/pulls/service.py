"""Pull request imports: read the pull request and its changed files from GitHub, import
and analyze the head commit, and scope test generation to the units the change touches."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testforge.audit.service import Actor, audit
from testforge.core.container import Container
from testforge.core.errors import AppError, NotFoundError
from testforge.projects.access import Principal
from testforge.pulls.diff import Span, changed_ranges, scope
from testforge.pulls.models import PullRequestImport
from testforge.sources import service as sources
from testforge.sources.github import GitHubError, parse_repo
from testforge.sources.models import CodeUnit, SourceImport


async def create(
    container: Container,
    session: AsyncSession,
    p: Principal,
    number: int,
    repo: str | None = None,
    *,
    source: str = "manual",
    actor: Actor | None = None,
) -> PullRequestImport:
    try:
        name = parse_repo(repo) if repo else p.project.github_repo
    except ValueError as exc:
        raise AppError(str(exc), code="invalid_repo") from None
    if not name:
        raise AppError(
            "Set the project's GitHub repository first (Settings, GitHub), or name it here",
            code="repo_required",
        )
    gh = await sources.github_client(container, p.project)
    try:
        pr = await gh.pull_request(name, number)
        files = await gh.pull_files(name, number)
    except GitHubError as exc:
        raise AppError(exc.message, code=exc.code) from None
    existing = await session.scalar(
        select(PullRequestImport).where(
            PullRequestImport.project_id == p.project_id,
            PullRequestImport.repo == name,
            PullRequestImport.number == number,
            PullRequestImport.head_sha == pr.head_sha,
        )
    )
    if existing is not None:
        return existing  # the same head commit was imported already (idempotent)
    imp = await sources.create_github_import(
        container, session, p, pr.head_repo, pr.head_sha, kind="pull_request", actor=actor
    )
    imp.commit_sha = pr.head_sha
    pull = PullRequestImport(
        project_id=p.project_id,
        repo=name,
        number=pr.number,
        title=pr.title[:500],
        author=pr.author[:200],
        base_ref=pr.base_ref,
        base_sha=pr.base_sha,
        head_ref=pr.head_ref,
        head_sha=pr.head_sha,
        import_id=imp.id,
        source=source,
        status="analyzing",
        changed_files=[
            {
                "path": f.path,
                "status": f.status,
                "additions": f.additions,
                "deletions": f.deletions,
                "previous_path": f.previous_path,
                "changed_lines": [list(r) for r in changed_ranges(f.patch)],
            }
            for f in files
        ],
        created_by=p.user_id,
    )
    session.add(pull)
    await session.flush()
    audit(
        session,
        actor or p.actor,
        "pull_request.imported",
        "pull_request",
        pull.id,
        repo=name,
        number=number,
        head=pr.head_sha,
        files=len(files),
        source=source,
        **p.audit_scope(),
    )
    await session.commit()
    return pull


async def scope_after_import(session: AsyncSession, imp: SourceImport) -> None:
    """Once the head commit is analyzed, record which units the change touches."""
    pulls = (
        await session.scalars(
            select(PullRequestImport).where(PullRequestImport.import_id == imp.id)
        )
    ).all()
    if not pulls:
        return
    rows = (await session.scalars(select(CodeUnit).where(CodeUnit.import_id == imp.id))).all()
    spans = [Span(str(u.id), u.file, u.start_line, u.end_line) for u in rows if u.kind != "class"]
    for pull in pulls:
        if imp.status == "failed":
            pull.status, pull.error = "failed", imp.error
            continue
        pull.scoped_unit_ids = scope(spans, pull.changed_files)
        pull.status = "ready"


async def list_pulls(session: AsyncSession, project_id: uuid.UUID) -> Sequence[PullRequestImport]:
    return (
        await session.scalars(
            select(PullRequestImport)
            .where(PullRequestImport.project_id == project_id)
            .order_by(PullRequestImport.created_at.desc())
            .limit(100)
        )
    ).all()


async def get(
    session: AsyncSession, project_id: uuid.UUID, pull_id: uuid.UUID
) -> PullRequestImport:
    pull = await session.scalar(
        select(PullRequestImport).where(
            PullRequestImport.id == pull_id, PullRequestImport.project_id == project_id
        )
    )
    if pull is None:
        raise NotFoundError("Pull request import not found")
    return pull
