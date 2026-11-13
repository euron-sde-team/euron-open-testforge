"""Anthropic Messages API. ``base_url`` is the API root (``https://api.anthropic.com``)."""

from __future__ import annotations

from typing import Any

from testforge.providers.adapters.base import (
    Adapter,
    call,
)
from testforge.providers.types import (
    Message,
    ModelRequest,
    ModelResponse,
    OnDelta,
    Usage,
)

API_VERSION = "2023-06-01"
_FINISH = {
    "end_turn": "stop",
    "tool_use": "tool_calls",
    "max_tokens": "length",
    "stop_sequence": "stop",
}


def to_wire(messages: tuple[Message, ...]) -> tuple[str, list[dict[str, Any]]]:
    """The system prompt and the alternating user/assistant turns. Tool results become
    ``tool_result`` blocks of a user turn, and consecutive turns of one role merge."""
    system = "\n\n".join(m.content for m in messages if m.role == "system" and m.content)
    turns: list[dict[str, Any]] = []
    blocks: list[dict[str, Any]]
    for m in messages:
        if m.role == "system":
            continue
        if m.role == "tool":
            role, blocks = (
                "user",
                [{"type": "tool_result", "tool_use_id": m.tool_call_id, "content": m.content}],
            )
        elif m.role == "assistant":
            role = "assistant"
            blocks = [{"type": "text", "text": m.content}] if m.content else []
            blocks += [
                {"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments or {}}
                for c in m.tool_calls
            ]
        else:
            role, blocks = "user", [{"type": "text", "text": m.content}]
        if not blocks:
            continue
        if turns and turns[-1]["role"] == role:
            turns[-1]["content"].extend(blocks)
        else:
            turns.append({"role": role, "content": blocks})
    return system, turns


def payload(req: ModelRequest) -> dict[str, Any]:
    system, turns = to_wire(req.messages)
    body: dict[str, Any] = {
        "model": req.model,
        "messages": turns,
        "max_tokens": req.max_tokens,
        "stream": False,
    }
    if system:
        body["system"] = system
    if req.temperature is not None:
        body["temperature"] = req.temperature
    if req.tools:
        body["tools"] = [
            {"name": t.name, "description": t.description, "input_schema": t.parameters}
            for t in req.tools
        ]
        body["tool_choice"] = {"type": "auto" if req.tool_choice == "auto" else "none"}
    return body


def _usage(raw: dict[str, Any] | None, base: Usage | None = None) -> Usage:
    raw = raw or {}
    u = base or Usage()
    if "input_tokens" in raw:
        u.input_tokens = int(raw.get("input_tokens") or 0) + int(
            raw.get("cache_creation_input_tokens") or 0
        )
        u.cached_input_tokens = int(raw.get("cache_read_input_tokens") or 0)
        u.input_tokens += u.cached_input_tokens
    if "output_tokens" in raw:
        u.output_tokens = int(raw.get("output_tokens") or 0)
    return u


def parse_response(body: dict[str, Any]) -> ModelResponse:
    text = "".join(b.get("text", "") for b in body.get("content") or [] if b.get("type") == "text")
    calls = [
        call(b.get("id", f"toolu_{i}"), b.get("name", ""), b.get("input") or {})
        for i, b in enumerate(body.get("content") or [])
        if b.get("type") == "tool_use"
    ]
    return ModelResponse(
        text=text,
        tool_calls=calls,
        usage=_usage(body.get("usage")),
        finish_reason=_FINISH.get(body.get("stop_reason") or "", body.get("stop_reason") or "stop"),
        model=body.get("model") or "",
    )


class AnthropicAdapter(Adapter):
    def _headers(self) -> dict[str, str]:
        h = {"anthropic-version": API_VERSION}
        if self.config.api_key:
            h["x-api-key"] = self.config.api_key
        return h

    async def list_models(self) -> list[str]:
        body = await self._get(f"{self.base}/v1/models?limit=1000", self._headers())
        return sorted(
            str(m.get("id")) for m in body.get("data") or [] if isinstance(m, dict) and m.get("id")
        )

    async def complete(self, req: ModelRequest, on_delta: OnDelta | None = None) -> ModelResponse:
        return parse_response(
            await self._post(f"{self.base}/v1/messages", payload(req), self._headers())
        )
