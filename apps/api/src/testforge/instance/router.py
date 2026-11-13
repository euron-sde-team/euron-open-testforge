"""HTTP endpoints for instance settings and self sign-up."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from redis.exceptions import RedisError

from testforge.auth.dependencies import Admin
from testforge.auth.router import _session
from testforge.auth.schemas import SignInOut
from testforge.core.deps import ContainerDep, SessionDep, client_ip
from testforge.core.errors import RateLimitedError
from testforge.instance import service
from testforge.instance.schemas import AdminSettings, PublicSettings, SettingsUpdate, SignupRequest
from testforge.limits.limiter import LimitDecision

router = APIRouter(prefix="/api/v1", tags=["instance"])
SIGNUP_RPM_PER_IP = 10


@router.get(
    "/instance/public", response_model=PublicSettings, summary="Settings the sign-in page needs"
)
async def public_settings(session: SessionDep, container: ContainerDep) -> PublicSettings:
    from sqlalchemy import select

    from testforge.users.models import User

    out = service.public(await service.get(session))
    out.needs_setup = not await session.scalar(select(User.id).limit(1))
    return out


@router.get("/instance/settings", response_model=AdminSettings, summary="Instance settings")
async def get_settings(_: Admin, session: SessionDep) -> AdminSettings:
    return service.admin(await service.get(session))


@router.patch(
    "/instance/settings", response_model=AdminSettings, summary="Change instance settings"
)
async def update_settings(body: SettingsUpdate, actor: Admin, session: SessionDep) -> AdminSettings:
    return service.admin(await service.update(session, body, actor))


@router.post(
    "/auth/signup",
    response_model=SignInOut,
    status_code=201,
    summary="Create an account and its organization (the first one is the admin), and sign in",
)
async def signup(
    body: SignupRequest,
    request: Request,
    response: Response,
    container: ContainerDep,
    session: SessionDep,
) -> SignInOut:
    ip = client_ip(request)
    try:
        decision = await container.kv.hit(f"signup:{ip}", SIGNUP_RPM_PER_IP)
    except (RedisError, OSError):
        decision = LimitDecision(allowed=True)
    if not decision.allowed:
        raise RateLimitedError(
            "Too many sign-ups from this address. Wait a minute and try again",
            headers={"retry-after": str(decision.retry_after_s)},
        )
    user = await service.signup(session, body, ip)
    response.headers["cache-control"] = "no-store"
    return _session(response, container, user)
