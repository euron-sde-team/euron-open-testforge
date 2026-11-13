"""Deterministic stand-ins for the services TestForge talks to, for tests, end-to-end runs
and the demo (no keys, no network, the same answer every time).

Model providers, in four wire formats, so every real provider adapter is exercised against
a real HTTP server:

* OpenAI (and every OpenAI-compatible gateway): POST /v1/chat/completions, GET /v1/models
* Anthropic: POST /anthropic/v1/messages, GET /anthropic/v1/models
* Gemini: POST /gemini/v1beta/models/{model}:generateContent, GET /gemini/v1beta/models
* Ollama: POST /ollama/api/chat, GET /ollama/api/tags

The answer comes from ``testforge.providers.mock.responder``, the same deterministic model
the in-process ``mock`` provider uses, so a prompt gets the same tests whichever path asked.
A model whose name contains ``placeholder`` answers like a careless model instead (tests
asserting nothing, or asserting True), to prove TestForge refuses them. Each family records
the credential it last received (``GET /_mock/auth``) so tests can prove the sealed key is
the one actually sent, and ``POST /_mock/fail`` makes the next calls fail with a status.

Also: a GitHub API serving the demo repositories and pull requests (``/github``, see
``github.py``), and a webhook receiver that records what it is sent (``/_mock/hooks``).
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from mockai.github import router as github_router
from testforge.generation.prompt import read_request
from testforge.providers.mock.responder import respond

app = FastAPI(title="TestForge mock services", docs_url=None, redoc_url=None)
app.include_router(github_router)
HOOKS: list[dict[str, Any]] = []


def _careless(user: str) -> str:
    """What a careless model writes: tests that cannot fail, or never run their assertion."""
    req = read_request(user) or {}
    tests = []
    for unit in req.get("units", [])[:5]:
        name = unit.get("name", "thing")
        module = unit.get("module", "app")
        if req.get("framework") == "vitest":
            code = (
                'import { expect, it } from "vitest";\n'
                f'import {{ {name} }} from "../{module}";\n\n'
                f'it("works", () => {{\n  {name};\n  expect(true).toBe(true);\n}});\n'
            )
        else:
            code = (
                f"from {module} import {unit.get('class_name') or name}\n\n\n"
                f"def test_{name}_placeholder():\n    assert True\n\n\n"
                f"def test_{name}_after_return():\n    return\n    assert {name}() == 1\n"
            )
        tests.append(
            {"name": f"test_{name}", "target": unit.get("id"), "kind": "unit", "code": code}
        )
    return json.dumps({"tests": tests})


def _answer(model: str, system: str, turns: list[tuple[str, str]]) -> str:
    user = "\n".join(text for role, text in turns if role == "user")
    if "placeholder" in (model or ""):
        return _careless(user)
    return respond(system, user)


AUTH: dict[str, str] = {}
CALLS: list[dict[str, Any]] = []
FAILURES: dict[str, list[int]] = defaultdict(list)


def _record(family: str, request: Request, header: str, system: str) -> None:
    AUTH[family] = request.headers.get(header, "")
    CALLS.append({"family": family, "task": system.splitlines()[0] if system else ""})


def _failure(family: str) -> JSONResponse | None:
    queue = FAILURES.get(family) or FAILURES.get("*")
    if not queue:
        return None
    status = queue.pop(0)
    return JSONResponse(
        {"error": {"message": "mock overload", "type": "server_error"}},
        status_code=status,
        headers={"retry-after": "0"},
    )


def _tokens(text: str) -> int:
    return max(len(text) // 4, 1)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/_mock/auth")
async def last_auth() -> dict[str, str]:
    return AUTH


@app.get("/_mock/calls")
async def calls() -> list[dict[str, Any]]:
    return CALLS


@app.post("/_mock/fail")
async def fail(status: int = 503, times: int = 1, family: str = "*") -> dict[str, int]:
    FAILURES[family].extend([status] * times)
    return {"queued": len(FAILURES[family])}


@app.post("/_mock/reset")
async def reset() -> dict[str, str]:
    AUTH.clear()
    CALLS.clear()
    FAILURES.clear()
    HOOKS.clear()
    return {"status": "ok"}


@app.post("/_mock/hooks/{name}")
async def receive_hook(name: str, request: Request) -> dict[str, str]:
    HOOKS.append(
        {
            "name": name,
            "headers": {k: v for k, v in request.headers.items() if k.startswith("x-")},
            "body": (await request.body()).decode("utf-8", "replace"),
        }
    )
    return {"status": "received"}


@app.get("/_mock/hooks")
async def hooks() -> list[dict[str, Any]]:
    return HOOKS


# OpenAI and compatible


@app.get("/v1/models")
async def openai_models(request: Request) -> dict[str, Any]:
    AUTH["v1"] = request.headers.get("authorization", "")
    return {"object": "list", "data": [{"id": "mock-tests-small", "object": "model"}]}


@app.post("/v1/chat/completions", response_model=None)
async def openai_chat(request: Request) -> JSONResponse:
    body = await request.json()
    system = "\n".join(
        str(m.get("content") or "") for m in body.get("messages", []) if m.get("role") == "system"
    )
    _record("v1", request, "authorization", system)
    if failed := _failure("v1"):
        return failed
    turns = [
        (str(m.get("role")), str(m.get("content") or ""))
        for m in body.get("messages", [])
        if m.get("role") != "system"
    ]
    text = _answer(str(body.get("model") or ""), system, turns)
    pin = _tokens(json.dumps(body.get("messages", [])))
    pout = _tokens(text)
    return JSONResponse(
        {
            "id": "chatcmpl-mock",
            "object": "chat.completion",
            "model": body.get("model", "mock-tests-small"),
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": text},
                }
            ],
            "usage": {"prompt_tokens": pin, "completion_tokens": pout, "total_tokens": pin + pout},
        }
    )


# Anthropic


@app.get("/anthropic/v1/models")
async def anthropic_models(request: Request) -> dict[str, Any]:
    AUTH["anthropic"] = request.headers.get("x-api-key", "")
    return {"data": [{"id": "mock-claude", "type": "model"}], "has_more": False}


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    return "".join(b.get("text", "") for b in content or [] if b.get("type") == "text")


@app.post("/anthropic/v1/messages", response_model=None)
async def anthropic(request: Request) -> JSONResponse:
    body = await request.json()
    system = _text(body.get("system") or "")
    _record("anthropic", request, "x-api-key", system)
    if failed := _failure("anthropic"):
        return failed
    turns = [(str(m["role"]), _text(m.get("content"))) for m in body.get("messages", [])]
    text = _answer(str(body.get("model") or ""), system, turns)
    return JSONResponse(
        {
            "id": "msg_mock",
            "type": "message",
            "role": "assistant",
            "model": body.get("model"),
            "content": [{"type": "text", "text": text}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": _tokens(json.dumps(body)), "output_tokens": _tokens(text)},
        }
    )


# Gemini


@app.get("/gemini/v1beta/models")
async def gemini_models(request: Request) -> dict[str, Any]:
    AUTH["gemini"] = request.headers.get("x-goog-api-key", "")
    return {
        "models": [
            {"name": "models/mock-gemini", "supportedGenerationMethods": ["generateContent"]}
        ]
    }


@app.post("/gemini/v1beta/models/{target}", response_model=None)
async def gemini(target: str, request: Request) -> JSONResponse:
    model, _, _ = target.partition(":")
    body = await request.json()
    system = "".join(
        p.get("text", "") for p in (body.get("systemInstruction") or {}).get("parts") or []
    )
    _record("gemini", request, "x-goog-api-key", system)
    if failed := _failure("gemini"):
        return failed
    turns = [
        (
            "assistant" if c.get("role") == "model" else "user",
            "".join(p.get("text", "") for p in c.get("parts") or []),
        )
        for c in body.get("contents") or []
    ]
    text = _answer(model, system, turns)
    return JSONResponse(
        {
            "candidates": [
                {"content": {"role": "model", "parts": [{"text": text}]}, "finishReason": "STOP"}
            ],
            "usageMetadata": {
                "promptTokenCount": _tokens(json.dumps(body)),
                "candidatesTokenCount": _tokens(text),
            },
            "modelVersion": model,
        }
    )


# Ollama


@app.get("/ollama/api/tags")
async def ollama_tags(request: Request) -> dict[str, Any]:
    AUTH["ollama"] = request.headers.get("authorization", "")
    return {"models": [{"name": "mock-coder:7b"}]}


@app.post("/ollama/api/chat", response_model=None)
async def ollama(request: Request) -> JSONResponse:
    body = await request.json()
    msgs = body.get("messages") or []
    system = "".join(m.get("content", "") for m in msgs if m.get("role") == "system")
    _record("ollama", request, "authorization", system)
    if failed := _failure("ollama"):
        return failed
    turns = [(m["role"], m.get("content", "")) for m in msgs if m.get("role") != "system"]
    text = _answer(str(body.get("model") or ""), system, turns)
    return JSONResponse(
        {
            "model": body.get("model"),
            "message": {"role": "assistant", "content": text},
            "done": True,
            "done_reason": "stop",
            "prompt_eval_count": _tokens(json.dumps(msgs)),
            "eval_count": _tokens(text),
        }
    )
