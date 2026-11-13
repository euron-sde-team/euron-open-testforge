"""Webhooks both ways.

Outbound: a project's webhooks receive ``run.finished`` (and the other events they chose)
as signed JSON. ``emit`` writes one delivery row per webhook in the transaction that
finished the run, and the scheduler sends due deliveries with retries and backoff
(``deliver_due``), so an event is never lost to a receiver being down for a while.

Inbound: GitHub (or a GitHub Action) posts ``pull_request`` events to
``/api/v1/hooks/github/{project_id}``; the body must carry GitHub's
``X-Hub-Signature-256`` for the project's webhook secret. An opened or updated pull
request is imported and scoped like one imported by hand.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import time
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testforge.audit.service import audit
from testforge.core.container import Container
from testforge.core.errors import AppError, NotFoundError
from testforge.core.net import resolves_safely
from testforge.observability import metrics
from testforge.projects.access import Principal
from testforge.projects.models import Project
from testforge.webhooks.models import Webhook, WebhookDelivery

log = logging.getLogger("testforge.webhooks")
SIGNATURE_HEADER = "X-TestForge-Signature"


def _ctx(webhook_id: uuid.UUID) -> str:
    return f"webhook:{webhook_id}:secret"


def sign(secret: str, body: bytes, now: int | None = None) -> str:
    ts = int(now if now is not None else time.time())
    mac = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={ts},v1={mac}"


async def create(
    container: Container,
    session: AsyncSession,
    p: Principal,
    name: str,
    url: str,
    events: list[str],
) -> tuple[Webhook, str]:
    secret = "whsec_" + secrets.token_urlsafe(24)
    hook = Webhook(
        project_id=p.project_id,
        name=name,
        url=url,
        events=sorted(set(events)),
        created_by=p.user_id,
    )
    hook.id = uuid.uuid4()
    hook.secret_sealed = await container.sealer.seal(secret, _ctx(hook.id))
    session.add(hook)
    audit(
        session,
        p.actor,
        "webhook.created",
        "webhook",
        hook.id,
        name=name,
        url=url,
        events=hook.events,
        **p.audit_scope(),
    )
    await session.commit()
    await session.refresh(hook)
    return hook, secret


async def list_hooks(session: AsyncSession, project_id: uuid.UUID) -> Sequence[Webhook]:
    return (
        await session.scalars(
            select(Webhook).where(Webhook.project_id == project_id).order_by(Webhook.created_at)
        )
    ).all()


async def get(session: AsyncSession, project_id: uuid.UUID, hook_id: uuid.UUID) -> Webhook:
    hook = await session.scalar(
        select(Webhook).where(Webhook.id == hook_id, Webhook.project_id == project_id)
    )
    if hook is None:
        raise NotFoundError("Webhook not found")
    return hook


async def delete(session: AsyncSession, p: Principal, hook: Webhook) -> None:
    audit(
        session, p.actor, "webhook.deleted", "webhook", hook.id, name=hook.name, **p.audit_scope()
    )
    await session.delete(hook)
    await session.commit()


async def deliveries(session: AsyncSession, hook_id: uuid.UUID) -> Sequence[WebhookDelivery]:
    return (
        await session.scalars(
            select(WebhookDelivery)
            .where(WebhookDelivery.webhook_id == hook_id)
            .order_by(WebhookDelivery.created_at.desc())
            .limit(50)
        )
    ).all()


async def emit(
    session: AsyncSession, project_id: uuid.UUID, event: str, payload: dict[str, Any]
) -> int:
    """Queue ``event`` for every enabled webhook of the project that asked for it (the
    caller commits, so the delivery exists exactly when the event happened)."""
    hooks = (
        await session.scalars(
            select(Webhook).where(Webhook.project_id == project_id, Webhook.enabled.is_(True))
        )
    ).all()
    n = 0
    for hook in hooks:
        if event in (hook.events or []):
            session.add(WebhookDelivery(webhook_id=hook.id, event=event, payload=payload))
            n += 1
    return n


async def _send(
    container: Container, hook: Webhook, delivery: WebhookDelivery
) -> tuple[bool, int | None, str | None]:
    settings = container.settings
    if not await resolves_safely(hook.url, allow_private=settings.webhook_allow_private):
        return False, None, "The webhook address resolves to a private or metadata address"
    secret = await container.sealer.open(hook.secret_sealed, _ctx(hook.id))
    body = json.dumps(delivery.payload, separators=(",", ":"), default=str).encode()
    headers = {
        "content-type": "application/json",
        "user-agent": "euron-open-testforge",
        "x-testforge-event": delivery.event,
        "x-testforge-delivery": str(delivery.id),
        SIGNATURE_HEADER.lower(): sign(secret, body),
    }
    try:
        resp = await container.http.post(
            hook.url, content=body, headers=headers, timeout=settings.webhook_timeout_s
        )
    except httpx.HTTPError as exc:
        return False, None, f"{exc.__class__.__name__}"
    return (
        200 <= resp.status_code < 300,
        resp.status_code,
        None if resp.status_code < 300 else resp.text[:300],
    )


async def deliver_due(container: Container, limit: int = 50) -> int:
    """Send due deliveries (the scheduler's task). Safe across replicas: rows are claimed
    with ``FOR UPDATE SKIP LOCKED`` and pushed past their next attempt before sending."""
    now = datetime.now(UTC)
    async with container.db.sessionmaker() as session:
        rows = (
            await session.scalars(
                select(WebhookDelivery)
                .where(WebhookDelivery.status == "pending", WebhookDelivery.next_attempt_at <= now)
                .order_by(WebhookDelivery.next_attempt_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        ).all()
        for d in rows:
            d.attempts += 1
            d.next_attempt_at = now + timedelta(seconds=min(30 * 2 ** (d.attempts - 1), 3600))
        await session.commit()
        for d in rows:
            hook = await session.get(Webhook, d.webhook_id)
            if hook is None or not hook.enabled:
                d.status = "failed"
                d.last_error = "the webhook was removed or turned off"
                continue
            ok, code, error = await _send(container, hook, d)
            d.last_status_code, d.last_error = code, error
            if ok:
                d.status, d.delivered_at = "delivered", datetime.now(UTC)
                metrics.WEBHOOK_DELIVERIES.labels("delivered").inc()
            elif d.attempts >= container.settings.webhook_max_attempts:
                d.status = "failed"
                metrics.WEBHOOK_DELIVERIES.labels("failed").inc()
            else:
                metrics.WEBHOOK_DELIVERIES.labels("retry").inc()
            await session.commit()
    return len(rows)


# ── Inbound: GitHub ──────────────────────────────────────────────────────────────────


def _github_ctx(project_id: uuid.UUID) -> str:
    return f"project:{project_id}:github_webhook_secret"


async def rotate_github_secret(container: Container, session: AsyncSession, p: Principal) -> str:
    secret = secrets.token_urlsafe(32)
    p.project.github_webhook_secret_sealed = await container.sealer.seal(
        secret, _github_ctx(p.project_id)
    )
    audit(
        session,
        p.actor,
        "github.webhook_secret_rotated",
        "project",
        p.project_id,
        **p.audit_scope(),
    )
    await session.commit()
    return secret


async def verify_github(
    container: Container, project: Project, body: bytes, header: str | None
) -> bool:
    if not project.github_webhook_secret_sealed or not header or not header.startswith("sha256="):
        return False
    secret = await container.sealer.open(
        project.github_webhook_secret_sealed, _github_ctx(project.id)
    )
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header)


def pull_request_event(event: str | None, payload: dict[str, Any]) -> tuple[str, int] | None:
    """(repo, number) for a pull request opened, reopened or updated; None otherwise."""
    if event != "pull_request":
        return None
    if payload.get("action") not in ("opened", "reopened", "synchronize", "ready_for_review"):
        return None
    pr = payload.get("pull_request") or {}
    repo = (payload.get("repository") or {}).get("full_name")
    number = pr.get("number") or payload.get("number")
    if not repo or not isinstance(number, int):
        raise AppError("The pull_request event has no repository or number", code="bad_event")
    return str(repo), number
