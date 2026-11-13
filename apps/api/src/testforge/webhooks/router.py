"""Outbound webhooks, the GitHub connection, and the inbound GitHub webhook."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Request, Response
from pydantic import Field, field_validator

from testforge.audit.service import Actor
from testforge.core.deps import ContainerDep, SessionDep
from testforge.core.errors import AppError, AuthenticationError, NotFoundError
from testforge.core.net import check_url
from testforge.core.schemas import ApiModel
from testforge.projects.access import Admin, Principal, Viewer
from testforge.projects.models import Project
from testforge.pulls import service as pulls
from testforge.webhooks import service
from testforge.webhooks.models import Webhook

router = APIRouter(prefix="/api/v1", tags=["webhooks"])

Event = Literal["run.finished", "generation.finished", "import.ready"]


def _default_events() -> list[Event]:
    return ["run.finished"]


class WebhookCreate(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    url: str = Field(max_length=1000)
    events: list[Event] = Field(default_factory=_default_events, min_length=1)

    @field_validator("url")
    @classmethod
    def _url(cls, v: str) -> str:
        return check_url(v)


class WebhookOut(ApiModel):
    id: uuid.UUID
    name: str
    url: str
    events: list[str]
    enabled: bool
    created_at: datetime


class WebhookCreated(WebhookOut):
    secret: str = Field(description="Shown once. Verify X-TestForge-Signature with it")


class DeliveryOut(ApiModel):
    id: uuid.UUID
    event: str
    status: str
    attempts: int
    last_status_code: int | None
    last_error: str | None
    created_at: datetime
    delivered_at: datetime | None


class GitHubSecret(ApiModel):
    secret: str = Field(description="Shown once. Paste it as the webhook secret in GitHub")
    url: str = Field(description="The payload URL to give GitHub (or a GitHub Action)")


@router.get(
    "/projects/{project_id}/webhooks", response_model=list[WebhookOut], summary="Outbound webhooks"
)
async def list_webhooks(p: Viewer, session: SessionDep) -> list[Webhook]:
    return list(await service.list_hooks(session, p.project_id))


@router.post(
    "/projects/{project_id}/webhooks",
    response_model=WebhookCreated,
    status_code=201,
    summary="Add a webhook (admins): signed JSON on run.finished and the events you choose",
)
async def create_webhook(
    body: WebhookCreate, p: Admin, session: SessionDep, container: ContainerDep
) -> WebhookCreated:
    hook, secret = await service.create(
        container, session, p, body.name, body.url, list(body.events)
    )
    return WebhookCreated(**WebhookOut.model_validate(hook).model_dump(), secret=secret)


@router.delete(
    "/projects/{project_id}/webhooks/{webhook_id}",
    status_code=204,
    summary="Remove a webhook (admins)",
)
async def delete_webhook(webhook_id: uuid.UUID, p: Admin, session: SessionDep) -> Response:
    await service.delete(session, p, await service.get(session, p.project_id, webhook_id))
    return Response(status_code=204)


@router.get(
    "/projects/{project_id}/webhooks/{webhook_id}/deliveries",
    response_model=list[DeliveryOut],
    summary="Recent deliveries of a webhook",
)
async def list_deliveries(
    webhook_id: uuid.UUID, p: Viewer, session: SessionDep
) -> list[DeliveryOut]:
    await service.get(session, p.project_id, webhook_id)
    return [DeliveryOut.model_validate(d) for d in await service.deliveries(session, webhook_id)]


@router.post(
    "/projects/{project_id}/github/webhook-secret",
    response_model=GitHubSecret,
    summary="Create (or rotate) the secret GitHub signs pull request events with (admins)",
)
async def rotate_github_secret(
    p: Admin, session: SessionDep, container: ContainerDep, request: Request
) -> GitHubSecret:
    secret = await service.rotate_github_secret(container, session, p)
    base = str(request.base_url).rstrip("/")
    return GitHubSecret(secret=secret, url=f"{base}/api/v1/hooks/github/{p.project_id}")


class HookAck(ApiModel):
    accepted: bool
    message: str
    pull_id: uuid.UUID | None = None


@router.post(
    "/hooks/github/{project_id}",
    response_model=HookAck,
    status_code=202,
    tags=["webhooks"],
    summary="GitHub webhook: import a pull request when it is opened or updated",
    description="Point a GitHub repository webhook (content type application/json, event "
    "`pull_request`) or a GitHub Action at this URL. The body must be signed with the project's "
    "webhook secret (`X-Hub-Signature-256`); anything else is refused with 401.",
)
async def github_hook(
    project_id: uuid.UUID, request: Request, session: SessionDep, container: ContainerDep
) -> HookAck:
    body = await request.body()
    project = await session.get(Project, project_id)
    signature = request.headers.get("x-hub-signature-256")
    if project is None or not await service.verify_github(container, project, body, signature):
        # The same answer for an unknown project and a bad signature.
        raise AuthenticationError("The webhook signature is not valid", code="bad_signature")
    event = request.headers.get("x-github-event")
    if event == "ping":
        return HookAck(accepted=True, message="pong")
    try:
        payload = json.loads(body)
    except ValueError:
        raise AppError("The body is not JSON", code="bad_event") from None
    target = service.pull_request_event(event, payload)
    if target is None:
        return HookAck(
            accepted=False, message=f"ignored: {event} {payload.get('action', '')}".strip()
        )
    repo, number = target
    actor = Actor(None, "github-webhook", "webhook", None)
    principal = Principal(project, "editor", actor)
    try:
        pull = await pulls.create(
            container, session, principal, number, repo, source="webhook", actor=actor
        )
    except NotFoundError:
        raise
    return HookAck(accepted=True, message=f"importing pull request #{number}", pull_id=pull.id)
