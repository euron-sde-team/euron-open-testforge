"""Test generation: from a request to a model call, through the assertion check, to tests
a developer reviews.

The API records the generation and queues it; the worker builds the prompt from the
analyzed source (``prompt.py``), calls the project's model provider, parses the answer and
runs every test through the assertion check (``checks.py``, A2). Only tests that pass the
check are stored and shown; refused ones leave their name and reason on the generation.
API generation then adds a test, built from the document itself, for any documented
operation the model skipped, so every operation is covered at least once (A7).
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from testforge.audit.service import Actor, audit
from testforge.core.container import Container
from testforge.core.errors import AppError, NotFoundError
from testforge.generation import checks, prompt, templates
from testforge.generation.models import GeneratedTest, Generation
from testforge.jobs import queue
from testforge.observability import metrics
from testforge.projects.access import Principal
from testforge.projects.models import Project
from testforge.providers import gateway
from testforge.providers import service as providers
from testforge.providers.models import ModelProvider
from testforge.providers.types import Message, ModelRequest, ProviderError
from testforge.pulls.models import PullRequestImport
from testforge.sandbox.runners import framework_for
from testforge.sources import service as sources
from testforge.sources.models import CodeUnit, SourceImport
from testforge.specs.models import ApiSpec
from testforge.usage import service as usage

log = logging.getLogger("testforge.generation")
HTTP_CALLS = {"get", "post", "put", "patch", "delete", "head", "options", "request"}
UNIT_KINDS = ("unit", "edge", "negative")


async def request(
    container: Container,
    session: AsyncSession,
    p: Principal,
    *,
    kinds: list[str],
    import_id: uuid.UUID | None = None,
    unit_ids: list[uuid.UUID] | None = None,
    pull_id: uuid.UUID | None = None,
    spec_id: uuid.UUID | None = None,
    provider_id: uuid.UUID | None = None,
    instructions: str = "",
) -> Generation:
    """Record a generation and queue it."""
    pull: PullRequestImport | None = None
    if pull_id is not None:
        pull = await session.scalar(
            select(PullRequestImport).where(
                PullRequestImport.id == pull_id, PullRequestImport.project_id == p.project_id
            )
        )
        if pull is None:
            raise NotFoundError("Pull request import not found")
        if pull.status != "ready" or pull.import_id is None:
            raise AppError(
                "The pull request is still being analyzed. Try again in a moment",
                code="pull_not_ready",
            )
        import_id = pull.import_id
        if unit_ids is None:
            unit_ids = [uuid.UUID(u) for u in pull.scoped_unit_ids]
        if not unit_ids:
            raise AppError(
                "This pull request changes no function, method or route TestForge found",
                code="nothing_in_scope",
            )
    if import_id is not None:
        imp = await sources.get_import(session, p.project_id, import_id)
        if imp.status != "ready":
            raise AppError("The import is not analyzed yet", code="import_not_ready")
    else:
        imp = await sources.current_import(session, p.project)
    spec: ApiSpec | None = None
    if spec_id is not None:
        spec = await session.scalar(
            select(ApiSpec).where(ApiSpec.id == spec_id, ApiSpec.project_id == p.project_id)
        )
        if spec is None:
            raise NotFoundError("OpenAPI document not found")
        kinds = ["api"]
        if not (imp.summary or {}).get("apps"):
            raise AppError(
                "API tests drive the project's FastAPI or Flask app in process, and the "
                "analysis found no app object (app = FastAPI() or app = Flask(...)) in this import",
                code="no_app",
            )
    elif "api" in kinds:
        raise AppError("Choose the OpenAPI document to write API tests from", code="spec_required")
    chosen = [str(u) for u in unit_ids] if unit_ids is not None else []
    if spec is None:
        found = await sources.units(
            session, imp.id, ids=[uuid.UUID(u) for u in chosen] if chosen else None
        )
        if not chosen:
            found = [u for u in found if u.exported and u.kind != "route"]
            untested = [
                u for u in found if not u.referenced_by_tests and not (u.covered_percent or 0)
            ]
            found = (untested or found)[: container.settings.max_units_per_generation]
        if not found:
            raise AppError("No code units to write tests for", code="no_units")
        chosen = [str(u.id) for u in found][: container.settings.max_units_per_generation]
    provider = (
        await providers.get_provider(session, p.project_id, provider_id)
        if provider_id
        else await providers.default_provider(session, p.project_id)
    )
    gen = Generation(
        project_id=p.project_id,
        import_id=imp.id,
        kinds=kinds,
        unit_ids=chosen,
        spec_id=spec.id if spec else None,
        pull_id=pull.id if pull else None,
        instructions=instructions[:2000],
        provider_id=provider.id,
        provider_kind=provider.kind,
        model=provider.model,
        requested_by=p.user_id,
        actor=p.actor.email or "",
    )
    session.add(gen)
    await session.flush()
    queue.enqueue(session, "generate", p.project_id, gen.id)
    audit(
        session,
        p.actor,
        "generation.requested",
        "generation",
        gen.id,
        kinds=kinds,
        units=len(chosen),
        spec=str(spec.id) if spec else None,
        pull_request=pull.number if pull else None,
        provider=provider.kind,
        model=provider.model,
        **p.audit_scope(),
    )
    await session.commit()
    await queue.notify(container)
    return gen


def _test_path(language: str, name: str, test_id: uuid.UUID) -> str:
    base = templates.slug(name.removeprefix("test_"))[:50]
    short = test_id.hex[:6]
    if language == "python":
        return f"{templates.PY_TEST_DIR}/test_{base}_{short}.py"
    ext = "ts" if language == "typescript" else "js"
    return f"{templates.JS_TEST_DIR}/{base}-{short}.test.{ext}"


def _targets_for(
    test: prompt.ParsedTest, units: dict[str, dict[str, Any]], mode: str
) -> tuple[set[str], str | None]:
    """Names the test must call, and the unit it belongs to (if it names one)."""
    if mode == "api":
        return set(HTTP_CALLS), None
    unit = units.get(test.target) or next(
        (u for u in units.values() if test.target in (u["qualname"], u["name"])), None
    )
    if unit is None:
        names = {u["name"] for u in units.values()} | {
            u["class_name"] for u in units.values() if u.get("class_name")
        }
        return names, None
    names = {unit["name"]}
    if unit.get("class_name"):
        names.add(unit["class_name"])
    return names, unit["id"]


async def _call(
    container: Container, provider: Any, system: str, user: str, gen: Generation
) -> str:
    adapter = await gateway.adapter(container, provider)
    started = time.perf_counter()
    try:
        resp = await gateway.complete(
            adapter,
            ModelRequest(
                model=provider.model,
                messages=(Message("system", system), Message("user", user)),
                max_tokens=8000,
                temperature=0.0,
            ),
        )
    except ProviderError:
        metrics.MODEL_CALLS.labels(provider.kind, "error").inc()
        raise
    finally:
        metrics.MODEL_LATENCY.labels(provider.kind).observe(time.perf_counter() - started)
    metrics.MODEL_CALLS.labels(provider.kind, "ok").inc()
    metrics.TOKENS.labels("input").inc(resp.usage.input_tokens)
    metrics.TOKENS.labels("output").inc(resp.usage.output_tokens)
    gen.input_tokens += resp.usage.input_tokens
    gen.output_tokens += resp.usage.output_tokens
    gen.model_ms += round((time.perf_counter() - started) * 1000)
    return resp.text


async def run(container: Container, session: AsyncSession, gen: Generation) -> None:
    """The worker's generation job."""
    gen.status = "running"
    await session.commit()
    imp = await session.get(SourceImport, gen.import_id)
    provider = await session.get(ModelProvider, gen.provider_id) if gen.provider_id else None
    project = await session.get(Project, gen.project_id)
    assert imp is not None and project is not None
    if provider is None:
        await _fail(session, gen, "no_provider", "The model provider was removed")
        return
    stored: list[GeneratedTest] = []
    rejections: list[dict[str, str]] = []
    try:
        if gen.spec_id is not None:
            stored, rejections = await _api_tests(container, session, gen, imp, provider)
        else:
            stored, rejections = await _unit_tests(container, session, gen, imp, provider)
    except ProviderError as exc:
        await _fail(session, gen, exc.code, exc.message)
        return
    except prompt.AnswerError as exc:
        await _fail(session, gen, "bad_answer", str(exc))
        return
    gen.accepted_count = len(stored)
    gen.rejected_count = len(rejections)
    gen.rejections = rejections
    gen.status = "done"
    gen.finished_at = datetime.now(UTC)
    for _ in stored:
        metrics.GENERATED_TESTS.labels("accepted").inc()
    for r in rejections:
        metrics.GENERATED_TESTS.labels(f"rejected_{r['code']}").inc()
    await usage.record(
        session,
        gen.project_id,
        gen.model,
        generations=1,
        tests_accepted=len(stored),
        tests_rejected=len(rejections),
        input_tokens=gen.input_tokens,
        output_tokens=gen.output_tokens,
    )
    audit(
        session,
        Actor(gen.requested_by, gen.actor or "worker", "system"),
        "generation.finished",
        "generation",
        gen.id,
        accepted=len(stored),
        rejected=len(rejections),
        rejections=[f"{r['name']}: {r['code']}" for r in rejections][:20],
        tests=[str(t.id) for t in stored][:100],
        model=gen.model,
        project_id=gen.project_id,
        org_id=project.org_id,
    )
    await session.commit()


async def _fail(session: AsyncSession, gen: Generation, code: str, message: str) -> None:
    gen.status = "failed"
    gen.error_code = code
    gen.error = message[:2000]
    gen.finished_at = datetime.now(UTC)
    await session.commit()


def _store(
    session: AsyncSession,
    gen: Generation,
    language: str,
    test: prompt.ParsedTest,
    result: checks.CheckResult,
    unit_id: str | None,
    operation: str | None,
) -> GeneratedTest:
    test_id = uuid.uuid4()
    row = GeneratedTest(
        id=test_id,
        project_id=gen.project_id,
        import_id=gen.import_id,
        generation_id=gen.id,
        unit_id=uuid.UUID(unit_id) if unit_id else None,
        operation=operation,
        kind=test.kind,
        language=language,
        framework=framework_for(language),
        name=test.name,
        file_path=_test_path(language, test.name, test_id),
        code=test.code,
        description=test.description,
        assertions=result.summary(),
    )
    session.add(row)
    return row


async def _unit_tests(
    container: Container,
    session: AsyncSession,
    gen: Generation,
    imp: SourceImport,
    provider: Any,
) -> tuple[list[GeneratedTest], list[dict[str, str]]]:
    rows = await sources.units(session, imp.id, ids=[uuid.UUID(u) for u in gen.unit_ids])
    classes = {
        (u.file, u.name): (u.details or {}).get("examples", [])
        for u in await sources.units(session, imp.id, kind="class")
    }
    budget = container.settings.prompt_source_chars
    by_language: dict[str, list[CodeUnit]] = {}
    for u in rows:
        by_language.setdefault(u.language, []).append(u)
    stored: list[GeneratedTest] = []
    rejected: list[dict[str, str]] = []
    for language, units in by_language.items():
        per_unit = max(400, budget // max(len(units), 1))
        payloads = {
            str(u.id): prompt.unit_payload(
                u,
                classes.get((u.file, (u.details or {}).get("class_name") or u.name), []),
                per_unit,
            )
            for u in units
        }
        req = {
            "mode": "unit",
            "language": language,
            "framework": framework_for(language),
            "kinds": [k for k in gen.kinds if k in UNIT_KINDS] or ["unit"],
            "units": list(payloads.values()),
            "instructions": gen.instructions,
        }
        system, user = prompt.build(req)
        tests = prompt.parse_answer(await _call(container, provider, system, user, gen))
        for t in tests:
            targets, unit_id = _targets_for(t, payloads, "unit")
            result = checks.check(language, t.code, targets)
            if not result.ok:
                rejected.append({"name": t.name, "code": result.code, "reason": result.reason})
                continue
            stored.append(_store(session, gen, language, t, result, unit_id, None))
    return stored, rejected


async def _api_tests(
    container: Container,
    session: AsyncSession,
    gen: Generation,
    imp: SourceImport,
    provider: Any,
) -> tuple[list[GeneratedTest], list[dict[str, str]]]:
    spec = await session.get(ApiSpec, gen.spec_id)
    assert spec is not None
    entry = (imp.summary or {}).get("apps", [])[0]
    app = {"framework": entry["framework"], "module": entry["module"], "attr": entry["attr"]}
    req: dict[str, Any] = {
        "mode": "api",
        "language": "python",
        "framework": "pytest",
        "app": app,
        "operations": spec.operations,
        "document": {"components": spec.document.get("components", {})},
        "instructions": gen.instructions,
    }
    system, user = prompt.build(req)
    tests = prompt.parse_answer(await _call(container, provider, system, user, gen))
    stored: list[GeneratedTest] = []
    rejected: list[dict[str, str]] = []
    keys = {op["key"] for op in spec.operations}
    covered: set[str] = set()
    for t in tests:
        result = checks.check("python", t.code, set(HTTP_CALLS))
        if not result.ok:
            rejected.append({"name": t.name, "code": result.code, "reason": result.reason})
            continue
        operation = t.target if t.target in keys else None
        if operation:
            covered.add(operation)
        t.kind = t.kind if t.kind in ("api", "negative") else "api"
        stored.append(_store(session, gen, "python", t, result, None, operation))
    # Every documented operation gets at least one test: the model's, or one built from
    # the document (status code and response shape) when the model skipped it.
    for op in spec.operations:
        if op["key"] in covered:
            continue
        d = templates.api_test(op, app, spec.document)
        result = checks.check("python", d.code, set(HTTP_CALLS))
        if result.ok:
            parsed = prompt.ParsedTest(d.name, d.target, d.kind, d.code, d.description)
            stored.append(_store(session, gen, "python", parsed, result, None, op["key"]))
            covered.add(op["key"])
    gen.operations_covered = sorted(covered)
    return stored, rejected


# ── Reading and reviewing ────────────────────────────────────────────────────────────


async def get_generation(
    session: AsyncSession, project_id: uuid.UUID, gen_id: uuid.UUID
) -> Generation:
    gen = await session.scalar(
        select(Generation).where(Generation.id == gen_id, Generation.project_id == project_id)
    )
    if gen is None:
        raise NotFoundError("Generation not found")
    return gen


async def list_generations(session: AsyncSession, project_id: uuid.UUID) -> Sequence[Generation]:
    return (
        await session.scalars(
            select(Generation)
            .where(Generation.project_id == project_id)
            .order_by(Generation.created_at.desc())
            .limit(50)
        )
    ).all()


async def list_tests(
    session: AsyncSession,
    project_id: uuid.UUID,
    *,
    status: str | None = None,
    generation_id: uuid.UUID | None = None,
    unit_id: uuid.UUID | None = None,
    kind: str | None = None,
    limit: int = 200,
) -> Sequence[GeneratedTest]:
    stmt = select(GeneratedTest).where(GeneratedTest.project_id == project_id)
    if status:
        stmt = stmt.where(GeneratedTest.status == status)
    if generation_id:
        stmt = stmt.where(GeneratedTest.generation_id == generation_id)
    if unit_id:
        stmt = stmt.where(GeneratedTest.unit_id == unit_id)
    if kind:
        stmt = stmt.where(GeneratedTest.kind == kind)
    return (
        await session.scalars(stmt.order_by(GeneratedTest.created_at.desc()).limit(limit))
    ).all()


async def get_test(
    session: AsyncSession, project_id: uuid.UUID, test_id: uuid.UUID
) -> GeneratedTest:
    test = await session.scalar(
        select(GeneratedTest).where(
            GeneratedTest.id == test_id, GeneratedTest.project_id == project_id
        )
    )
    if test is None:
        raise NotFoundError("Test not found")
    return test


async def review(
    session: AsyncSession, p: Principal, test: GeneratedTest, status: str
) -> GeneratedTest:
    if test.status != status:
        test.status = status
        test.reviewed_by = p.user_id
        audit(
            session,
            p.actor,
            f"test.{status}",
            "generated_test",
            test.id,
            name=test.name,
            file=test.file_path,
            **p.audit_scope(),
        )
        await session.commit()
    return test


async def review_many(
    session: AsyncSession, p: Principal, ids: list[uuid.UUID], status: str
) -> int:
    tests = (
        await session.scalars(
            select(GeneratedTest).where(
                GeneratedTest.project_id == p.project_id, GeneratedTest.id.in_(ids)
            )
        )
    ).all()
    changed = [t for t in tests if t.status != status]
    for t in changed:
        t.status = status
        t.reviewed_by = p.user_id
    if changed:
        audit(
            session,
            p.actor,
            f"test.{status}",
            "generated_test",
            None,
            tests=[str(t.id) for t in changed][:200],
            count=len(changed),
            **p.audit_scope(),
        )
        await session.commit()
    return len(changed)


async def counts(session: AsyncSession, project_id: uuid.UUID) -> dict[str, int]:
    rows = (
        await session.execute(
            select(GeneratedTest.status, func.count())
            .where(GeneratedTest.project_id == project_id)
            .group_by(GeneratedTest.status)
        )
    ).all()
    return {str(s): int(n) for s, n in rows}
