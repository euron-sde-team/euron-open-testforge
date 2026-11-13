"""Model providers: create, change, test, choose the project's default.

Keys and extra headers are sealed with the key sealer (local AES-GCM or KMS) under a
context bound to the provider id, so a sealed value copied to another row does not open.
The API returns only whether a key is stored.

Base URLs never point at instance metadata (``check_url``). Private addresses are allowed
for providers by default (a local Ollama or vLLM is the normal case); set
``PROVIDER_ALLOW_PRIVATE=false`` to allow hosted providers only.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from testforge.audit.service import audit
from testforge.core.container import Container
from testforge.core.errors import AppError, ConflictError, NotFoundError
from testforge.core.net import host_of, is_private_host, resolves_safely
from testforge.projects.access import Principal
from testforge.providers.adapters import (
    DEFAULT_BASE_URLS,
    DEFAULT_MODELS,
    ProviderConfig,
    adapter_for,
)
from testforge.providers.models import ModelProvider
from testforge.providers.schemas import ProviderCreate, ProviderOut, ProviderTest, ProviderUpdate
from testforge.providers.types import ProviderError


def _ctx(provider_id: uuid.UUID, what: str) -> str:
    return f"model_provider:{provider_id}:{what}"


async def open_headers(container: Container, p: ModelProvider) -> dict[str, str]:
    if p.headers_sealed is None:
        return {}
    value = json.loads(await container.sealer.open(p.headers_sealed, _ctx(p.id, "headers")))
    return {str(k): str(v) for k, v in value.items()}


async def provider_out(container: Container, p: ModelProvider) -> ProviderOut:
    return ProviderOut(
        id=p.id,
        name=p.name,
        kind=p.kind,
        model=p.model,
        base_url=p.base_url,
        has_api_key=p.api_key_sealed is not None,
        header_names=sorted((await open_headers(container, p)).keys()),
        enabled=p.enabled,
        is_default=p.is_default,
        timeout_s=p.timeout_s,
        last_test_at=p.last_test_at,
        last_test_ok=p.last_test_ok,
        last_test_message=p.last_test_message,
        created_at=p.created_at,
    )


async def _check_reachable(container: Container, url: str) -> None:
    allow_private = container.settings.provider_allow_private
    if not allow_private and is_private_host(host_of(url)):
        raise AppError(
            "The provider URL is a private address, which this deployment does not allow "
            "(PROVIDER_ALLOW_PRIVATE=false)",
            code="provider_private",
        )
    if not await resolves_safely(url, allow_private=allow_private):
        raise AppError(
            "The provider URL resolves to a forbidden address", code="provider_forbidden"
        )


async def config_of(container: Container, p: ModelProvider) -> ProviderConfig:
    key = (
        await container.sealer.open(p.api_key_sealed, _ctx(p.id, "api_key"))
        if p.api_key_sealed is not None
        else None
    )
    if p.kind != "mock":
        await _check_reachable(container, p.base_url)
    return ProviderConfig(
        kind=p.kind,
        base_url=p.base_url,
        api_key=key,
        headers=await open_headers(container, p),
        timeout_s=min(p.timeout_s, container.settings.model_timeout_s),
    )


async def list_providers(
    container: Container, session: AsyncSession, project_id: uuid.UUID
) -> list[ProviderOut]:
    rows = (
        await session.scalars(
            select(ModelProvider)
            .where(ModelProvider.project_id == project_id)
            .order_by(ModelProvider.is_default.desc(), ModelProvider.name)
        )
    ).all()
    return [await provider_out(container, r) for r in rows]


async def get_provider(
    session: AsyncSession, project_id: uuid.UUID, provider_id: uuid.UUID
) -> ModelProvider:
    row = await session.scalar(
        select(ModelProvider).where(
            ModelProvider.id == provider_id, ModelProvider.project_id == project_id
        )
    )
    if row is None:
        raise NotFoundError("Provider not found")
    return row


async def default_provider(session: AsyncSession, project_id: uuid.UUID) -> ModelProvider:
    """The provider a generation uses when it names none: the project's default, else its
    only enabled provider."""
    rows = (
        await session.scalars(
            select(ModelProvider)
            .where(ModelProvider.project_id == project_id, ModelProvider.enabled.is_(True))
            .order_by(ModelProvider.is_default.desc(), ModelProvider.created_at)
        )
    ).all()
    if not rows:
        raise AppError(
            "This project has no model provider yet. An admin adds one under Settings, "
            "Model providers (the built-in mock works without a key)",
            code="no_provider",
        )
    return rows[0]


async def _clear_default(session: AsyncSession, project_id: uuid.UUID) -> None:
    await session.execute(
        update(ModelProvider)
        .where(ModelProvider.project_id == project_id, ModelProvider.is_default.is_(True))
        .values(is_default=False)
    )


async def create_provider(
    container: Container, session: AsyncSession, p: Principal, data: ProviderCreate
) -> ModelProvider:
    if await session.scalar(
        select(ModelProvider.id).where(
            ModelProvider.project_id == p.project_id, ModelProvider.name == data.name
        )
    ):
        raise ConflictError(
            "A provider with this name exists in the project", code="provider_name_taken"
        )
    base_url = data.base_url or DEFAULT_BASE_URLS.get(data.kind, "")
    if data.kind == "openai_compatible" and not base_url:
        raise AppError("An OpenAI-compatible provider needs its base URL", code="base_url_required")
    if data.kind == "mock":
        base_url = ""
    else:
        await _check_reachable(container, base_url)
    model = data.model.strip() or DEFAULT_MODELS.get(data.kind, "")
    if not model:
        raise AppError("Name the model to use, e.g. llama-3.3-70b", code="model_required")
    first = not await session.scalar(
        select(ModelProvider.id).where(ModelProvider.project_id == p.project_id).limit(1)
    )
    row = ModelProvider(
        id=uuid.uuid4(),
        project_id=p.project_id,
        name=data.name,
        kind=data.kind,
        base_url=base_url,
        model=model,
        enabled=data.enabled,
        timeout_s=data.timeout_s,
        created_by=p.user_id,
    )
    if data.is_default or first:
        await _clear_default(session, p.project_id)
        row.is_default = True
    if data.api_key:
        row.api_key_sealed = await container.sealer.seal(data.api_key, _ctx(row.id, "api_key"))
    if data.headers:
        row.headers_sealed = await container.sealer.seal(
            json.dumps(data.headers), _ctx(row.id, "headers")
        )
    session.add(row)
    audit(
        session,
        p.actor,
        "provider.created",
        "model_provider",
        row.id,
        name=row.name,
        kind=row.kind,
        model=row.model,
        **p.audit_scope(),
    )
    await session.commit()
    return row


async def update_provider(
    container: Container,
    session: AsyncSession,
    p: Principal,
    row: ModelProvider,
    data: ProviderUpdate,
) -> ModelProvider:
    changes = data.model_dump(exclude_unset=True)
    fields = sorted(changes)
    if changes.get("base_url") and row.kind != "mock":
        await _check_reachable(container, changes["base_url"])
        row.base_url = changes["base_url"]
    if changes.get("model"):
        row.model = changes["model"].strip()
    if "api_key" in changes:
        key = changes["api_key"]
        row.api_key_sealed = (
            await container.sealer.seal(key, _ctx(row.id, "api_key")) if key else None
        )
    if changes.get("headers") is not None:
        headers = changes["headers"]
        row.headers_sealed = (
            await container.sealer.seal(json.dumps(headers), _ctx(row.id, "headers"))
            if headers
            else None
        )
    for name in ("timeout_s", "enabled"):
        if changes.get(name) is not None:
            setattr(row, name, changes[name])
    if changes.get("is_default") is True:
        await _clear_default(session, p.project_id)
        await session.flush()
        row.is_default = True
    elif changes.get("is_default") is False:
        row.is_default = False
    audit(
        session,
        p.actor,
        "provider.updated",
        "model_provider",
        row.id,
        fields=fields,
        **p.audit_scope(),
    )
    await session.commit()
    await session.refresh(row)
    return row


async def delete_provider(session: AsyncSession, p: Principal, row: ModelProvider) -> None:
    audit(
        session,
        p.actor,
        "provider.deleted",
        "model_provider",
        row.id,
        name=row.name,
        **p.audit_scope(),
    )
    await session.delete(row)
    await session.commit()


async def test_provider(
    container: Container, session: AsyncSession, row: ModelProvider
) -> ProviderTest:
    """List the provider's models with the stored key: proves the URL and the key work."""
    started = time.monotonic()
    try:
        models = await adapter_for(await config_of(container, row), container.http).list_models()
        ok = True
        message = f"Connected. {len(models)} models available"
        if row.model not in models and models and row.kind != "mock":
            message += f"; {row.model} is not among them, check the model name"
    except (ProviderError, AppError) as exc:
        models, ok, message = [], False, exc.message
    row.last_test_at = datetime.now(UTC)
    row.last_test_ok = ok
    row.last_test_message = message[:500]
    await session.commit()
    return ProviderTest(
        ok=ok,
        message=message,
        latency_ms=int((time.monotonic() - started) * 1000),
        models=models[:500],
    )
