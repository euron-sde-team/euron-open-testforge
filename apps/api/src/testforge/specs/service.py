"""OpenAPI documents imported for API test generation."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testforge.audit.service import audit
from testforge.core.errors import AppError, NotFoundError
from testforge.projects.access import Principal
from testforge.specs import openapi
from testforge.specs.models import ApiSpec


async def create(session: AsyncSession, p: Principal, text: str, max_bytes: int) -> ApiSpec:
    if len(text.encode()) > max_bytes:
        raise AppError(f"The document is larger than {max_bytes} bytes", code="spec_too_large")
    try:
        doc = openapi.load(text)
    except openapi.SpecError as exc:
        raise AppError(str(exc), code="invalid_spec") from None
    ops = openapi.operations(doc)
    if not ops:
        raise AppError("The document has no operations", code="invalid_spec")
    info = doc.get("info") or {}
    spec = ApiSpec(
        project_id=p.project_id,
        title=str(info.get("title") or "API")[:200],
        version=str(info.get("version") or "")[:64],
        document=doc,
        operations=ops,
        operation_count=len(ops),
        created_by=p.user_id,
    )
    session.add(spec)
    await session.flush()
    audit(
        session,
        p.actor,
        "spec.imported",
        "api_spec",
        spec.id,
        title=spec.title,
        operations=len(ops),
        **p.audit_scope(),
    )
    await session.commit()
    return spec


async def list_specs(session: AsyncSession, project_id: uuid.UUID) -> Sequence[ApiSpec]:
    return (
        await session.scalars(
            select(ApiSpec)
            .where(ApiSpec.project_id == project_id)
            .order_by(ApiSpec.created_at.desc())
        )
    ).all()


async def get(session: AsyncSession, project_id: uuid.UUID, spec_id: uuid.UUID) -> ApiSpec:
    spec = await session.scalar(
        select(ApiSpec).where(ApiSpec.id == spec_id, ApiSpec.project_id == project_id)
    )
    if spec is None:
        raise NotFoundError("OpenAPI document not found")
    return spec
