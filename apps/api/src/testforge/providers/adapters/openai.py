"""OpenAI chat completions, also spoken by every OpenAI-compatible endpoint (vLLM, LM
Studio, Groq, Together, the Euri gateway, TokenShield, SmartRouter). ``base_url`` ends in
``/v1``."""

from __future__ import annotations

import json
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
    ProviderError,
    Usage,
)


def to_wire(m: Message) -> dict[str, Any]:
    if m.role == "tool":
        return {"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content}
    out: dict[str, Any] = {"role": m.role, "content": m.content}
    if m.tool_calls:
        out["tool_calls"] = [
            {
                "id": c.id,
                "type": "function",
                "function": {
                    "name": c.name,
                    "arguments": c.raw_arguments or json.dumps(c.arguments or {}),
                },
            }
            for c in m.tool_calls
        ]
        if not m.content:
            out["content"] = None
    return out


def payload(req: ModelRequest) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": req.model,
        "messages": [to_wire(m) for m in req.messages],
        "max_completion_tokens": req.max_tokens,
        "stream": False,
    }
    if req.temperature is not None:
        body["temperature"] = req.temperature
    if req.tools:
        body["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in req.tools
        ]
        body["tool_choice"] = req.tool_choice
    return body


def _usage(raw: dict[str, Any] | None) -> Usage:
    raw = raw or {}
    details = raw.get("prompt_tokens_details") or {}
    return Usage(
        input_tokens=int(raw.get("prompt_tokens") or 0),
        output_tokens=int(raw.get("completion_tokens") or 0),
        cached_input_tokens=int(details.get("cached_tokens") or 0),
    )


def parse_response(body: dict[str, Any]) -> ModelResponse:
    choices = body.get("choices") or []
    if not choices:
        raise ProviderError("The provider returned no choices", retryable=True)
    msg = choices[0].get("message") or {}
    calls = [
        call(
            c.get("id") or f"call_{i}",
            (c.get("function") or {}).get("name", ""),
            (c.get("function") or {}).get("arguments"),
        )
        for i, c in enumerate(msg.get("tool_calls") or [])
    ]
    return ModelResponse(
        text=msg.get("content") or "",
        tool_calls=calls,
        usage=_usage(body.get("usage")),
        finish_reason=choices[0].get("finish_reason") or ("tool_calls" if calls else "stop"),
        model=body.get("model") or "",
        usage_reported=bool(body.get("usage")),
    )


class OpenAIAdapter(Adapter):
    def _headers(self) -> dict[str, str]:
        return {"authorization": f"Bearer {self.config.api_key}"} if self.config.api_key else {}

    async def list_models(self) -> list[str]:
        body = await self._get(f"{self.base}/models", self._headers())
        return sorted(
            str(m.get("id")) for m in body.get("data") or [] if isinstance(m, dict) and m.get("id")
        )

    async def complete(self, req: ModelRequest, on_delta: OnDelta | None = None) -> ModelResponse:
        return parse_response(
            await self._post(f"{self.base}/chat/completions", payload(req), self._headers())
        )
