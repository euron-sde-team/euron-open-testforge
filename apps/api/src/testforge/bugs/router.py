"""Failure analysis: explain a failed test from the run that produced it (A8)."""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter
from pydantic import Field
from sqlalchemy import select

from testforge.core.deps import ContainerDep, SessionDep
from testforge.core.errors import AppError, NotFoundError
from testforge.core.schemas import ApiModel
from testforge.generation.prompt import REQUEST_CLOSE, REQUEST_OPEN
from testforge.projects.access import Generator, Viewer
from testforge.providers import gateway
from testforge.providers import service as providers
from testforge.providers.types import Message, ModelRequest, ProviderError
from testforge.runs import service as runs
from testforge.runs.models import TestCaseResult

router = APIRouter(prefix="/api/v1/projects/{project_id}", tags=["bugs"])

SYSTEM = (
    "You explain why a unit test failed, to the developer who owns the code. You get the "
    "failing assertion, the actual and expected values captured when it failed, the test's "
    "code and the code under test. In three sentences at most: what the code did, what the "
    "test expected, and the most likely fix. Do not invent values you were not given."
)


class FailureOut(ApiModel):
    run_id: uuid.UUID
    case_id: uuid.UUID
    test: str
    outcome: str
    failure: dict[str, Any]
    # Written by the project's model from the captured values (only when asked for).
    model_explanation: str | None = None


class AnalyzeRequest(ApiModel):
    run_id: uuid.UUID
    case_id: uuid.UUID
    # Also ask the project's model for a narrative (the structured explanation is always
    # there, and never needs a model or a second run).
    use_model: bool = False
    provider_id: uuid.UUID | None = Field(None)


@router.get(
    "/runs/{run_id}/failures",
    response_model=list[FailureOut],
    summary="Every failure of a run, explained",
)
async def failures(run_id: uuid.UUID, p: Viewer, session: SessionDep) -> list[FailureOut]:
    await runs.get(session, p.project_id, run_id)
    return [
        FailureOut(
            run_id=run_id, case_id=c.id, test=c.name, outcome=c.outcome, failure=c.failure or {}
        )
        for c in await runs.cases(session, run_id)
        if c.outcome in ("failed", "error")
    ]


@router.post(
    "/bugs/analyze",
    response_model=FailureOut,
    summary="Explain one failed test from the values its run captured (no second run)",
)
async def analyze(
    body: AnalyzeRequest, p: Generator, session: SessionDep, container: ContainerDep
) -> FailureOut:
    run = await runs.get(session, p.project_id, body.run_id)
    case = await session.scalar(
        select(TestCaseResult).where(
            TestCaseResult.id == body.case_id, TestCaseResult.run_id == run.id
        )
    )
    if case is None:
        raise NotFoundError("No such test case in this run")
    if case.outcome not in ("failed", "error") or not case.failure:
        raise AppError("This test did not fail", code="not_failed")
    out = FailureOut(
        run_id=run.id, case_id=case.id, test=case.name, outcome=case.outcome, failure=case.failure
    )
    if body.use_model:
        provider = (
            await providers.get_provider(session, p.project_id, body.provider_id)
            if body.provider_id
            else await providers.default_provider(session, p.project_id)
        )
        req = {"mode": "explain", "failure": {"test": case.name, **case.failure}}
        user = f"{REQUEST_OPEN}\n{json.dumps(req, default=str)}\n{REQUEST_CLOSE}"
        try:
            adapter = await gateway.adapter(container, provider)
            resp = await gateway.complete(
                adapter,
                ModelRequest(
                    model=provider.model,
                    messages=(Message("system", SYSTEM), Message("user", user)),
                    max_tokens=600,
                    temperature=0.0,
                ),
            )
        except ProviderError as exc:
            raise AppError(exc.message, code=exc.code) from None
        out.model_explanation = resp.text.strip()[:4000]
    return out
