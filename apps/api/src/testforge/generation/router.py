"""Test generation, the generated tests, and reviewing them."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from testforge.core.deps import ContainerDep, SessionDep
from testforge.core.errors import RateLimitedError
from testforge.generation import service
from testforge.generation.models import Generation
from testforge.generation.schemas import (
    BulkResult,
    BulkReview,
    GenerateRequest,
    GenerationOut,
    TestDetail,
    TestOut,
    TestReview,
)
from testforge.jobs import queue
from testforge.projects.access import Editor, Generator, Principal, Viewer
from testforge.sources.models import CodeUnit

router = APIRouter(prefix="/api/v1/projects/{project_id}", tags=["tests"])


async def _limit(container: ContainerDep, p: Principal) -> None:
    try:
        decision = await container.kv.hit(
            f"generate:{p.project_id}", container.settings.generate_rpm
        )
    except Exception:
        return  # the limiter is a convenience; Redis being down never blocks work
    if not decision.allowed:
        raise RateLimitedError(
            "Too many generations for this project in the last minute. Wait and try again",
            headers={"retry-after": str(decision.retry_after_s)},
        )


@router.post(
    "/tests/generate",
    response_model=GenerationOut,
    status_code=202,
    summary="Generate tests from the analyzed source (or an OpenAPI document)",
    description="Every generated test passes the assertion check before it is stored: one with "
    "no meaningful, reachable assertion about the code under test is refused and only its name "
    "and reason are kept (`rejections`). Pass `wait` (seconds) to return when it is done.",
)
async def generate(
    body: GenerateRequest,
    p: Generator,
    session: SessionDep,
    container: ContainerDep,
    wait: float = Query(0, ge=0, le=300),
) -> Generation:
    await _limit(container, p)
    gen = await service.request(
        container,
        session,
        p,
        kinds=list(body.kinds),
        import_id=body.import_id,
        unit_ids=body.unit_ids,
        pull_id=body.pull_id,
        spec_id=body.spec_id,
        provider_id=body.provider_id,
        instructions=body.instructions,
    )
    if wait:
        await queue.wait_for(container, gen.id, wait)
        await session.refresh(gen)
    return gen


@router.get("/generations", response_model=list[GenerationOut], summary="Generations, newest first")
async def list_generations(p: Viewer, session: SessionDep) -> list[Generation]:
    return list(await service.list_generations(session, p.project_id))


@router.get("/generations/{generation_id}", response_model=GenerationOut, summary="One generation")
async def get_generation(
    generation_id: uuid.UUID,
    p: Viewer,
    session: SessionDep,
    container: ContainerDep,
    wait: float = Query(0, ge=0, le=300),
) -> Generation:
    gen = await service.get_generation(session, p.project_id, generation_id)
    if wait and gen.status in ("queued", "running"):
        await queue.wait_for(container, gen.id, wait)
        await session.refresh(gen)
    return gen


@router.get("/tests", response_model=list[TestOut], summary="Generated tests")
async def list_tests(
    p: Viewer,
    session: SessionDep,
    status: str | None = Query(None, pattern=r"^(proposed|accepted|discarded)$"),
    generation_id: uuid.UUID | None = None,
    unit_id: uuid.UUID | None = None,
    kind: str | None = Query(None, pattern=r"^(unit|edge|negative|api)$"),
) -> list[TestOut]:
    rows = await service.list_tests(
        session,
        p.project_id,
        status=status,
        generation_id=generation_id,
        unit_id=unit_id,
        kind=kind,
    )
    return [TestOut.model_validate(t) for t in rows]


@router.get(
    "/tests/{test_id}",
    response_model=TestDetail,
    summary="One test: its code, assertions and description",
)
async def get_test(test_id: uuid.UUID, p: Viewer, session: SessionDep) -> TestDetail:
    test = await service.get_test(session, p.project_id, test_id)
    out = TestDetail.model_validate(test)
    if test.unit_id:
        unit = await session.get(CodeUnit, test.unit_id)
        if unit is not None:
            out.unit = {
                "id": str(unit.id),
                "kind": unit.kind,
                "qualname": unit.qualname,
                "file": unit.file,
                "start_line": unit.start_line,
                "end_line": unit.end_line,
                "signature": unit.signature,
                "source": unit.source,
            }
    return out


@router.patch("/tests/{test_id}", response_model=TestOut, summary="Accept or discard a test")
async def review_test(
    test_id: uuid.UUID, body: TestReview, p: Editor, session: SessionDep
) -> TestOut:
    test = await service.get_test(session, p.project_id, test_id)
    return TestOut.model_validate(await service.review(session, p, test, body.status))


@router.post(
    "/tests/review", response_model=BulkResult, summary="Accept or discard many tests at once"
)
async def review_many(body: BulkReview, p: Editor, session: SessionDep) -> BulkResult:
    return BulkResult(changed=await service.review_many(session, p, body.ids, body.status))


@router.post(
    "/tests/{test_id}/regenerate",
    response_model=GenerationOut,
    status_code=202,
    summary="Write this test again (the old one is discarded)",
)
async def regenerate(
    test_id: uuid.UUID,
    p: Generator,
    session: SessionDep,
    container: ContainerDep,
    wait: float = Query(0, ge=0, le=300),
) -> Generation:
    test = await service.get_test(session, p.project_id, test_id)
    await _limit(container, p)
    old = await service.get_generation(session, p.project_id, test.generation_id)
    gen = await service.request(
        container,
        session,
        p,
        kinds=[test.kind] if test.kind != "api" else ["api"],
        import_id=test.import_id,
        unit_ids=[test.unit_id] if test.unit_id else None,
        spec_id=old.spec_id,
        instructions=old.instructions,
    )
    await service.review(session, p, test, "discarded")
    if wait:
        await queue.wait_for(container, gen.id, wait)
        await session.refresh(gen)
    return gen
