"""Request body limits and request ids, at the ASGI level."""

from __future__ import annotations

import json
from typing import Any

import pytest

from testforge.core.config import Settings
from testforge.core.middleware import BodySizeLimitMiddleware, RequestContextMiddleware

Message = dict[str, Any]


async def _echo(scope: dict[str, Any], receive: Any, send: Any) -> None:
    body = b""
    while True:
        m = await receive()
        body += m.get("body", b"")
        if not m.get("more_body"):
            break
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": str(len(body)).encode()})


async def _call(
    app: Any, path: str, chunks: list[bytes], headers: list[tuple[bytes, bytes]]
) -> list[Message]:
    sent: list[Message] = []
    queue = [
        {"type": "http.request", "body": c, "more_body": i < len(chunks) - 1}
        for i, c in enumerate(chunks)
    ]

    async def receive() -> Message:
        return queue.pop(0) if queue else {"type": "http.disconnect"}

    async def send(m: Message) -> None:
        sent.append(m)

    scope = {"type": "http", "method": "POST", "path": path, "headers": headers}
    await app(scope, receive, send)
    return sent


@pytest.mark.parametrize("declared", [True, False])
async def test_bodies_over_the_limit_get_413(declared: bool) -> None:
    app = BodySizeLimitMiddleware(_echo, Settings(max_body_bytes=1_000_000))  # type: ignore[arg-type]
    chunks = [b"x" * 600_000, b"x" * 600_000]
    headers = [(b"content-length", b"1200000")] if declared else []
    sent = await _call(app, "/api/v1/projects/p/chat", chunks, headers)
    assert sent[0]["status"] == 413
    assert json.loads(sent[1]["body"])["error"]["code"] == "payload_too_large"
    ok = await _call(app, "/api/v1/projects/p/chat", [b"x" * 10], [])
    assert ok[0]["status"] == 200 and ok[1]["body"] == b"10"


async def test_a_signed_in_zip_upload_may_be_larger() -> None:
    app = BodySizeLimitMiddleware(
        _echo,
        Settings(max_body_bytes=1_000_000, max_upload_bytes=5_000_000),  # type: ignore[arg-type]
    )
    big = [b"x" * 2_000_000]
    anon = await _call(app, "/api/v1/projects/p/imports/zip", big, [])
    assert anon[0]["status"] == 413
    keyed = await _call(
        app,
        "/api/v1/projects/p/imports/zip",
        big,
        [(b"x-api-key", b"tfk_0123456789ab_secret")],
    )
    assert keyed[0]["status"] == 200


async def test_every_response_carries_a_request_id() -> None:
    app = RequestContextMiddleware(_echo)
    sent = await _call(app, "/x", [b"{}"], [(b"x-request-id", b"abc123")])
    assert (b"x-request-id", b"abc123") in sent[0]["headers"]
