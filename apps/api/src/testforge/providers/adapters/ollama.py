"""Ollama's native chat API (a local model server). ``base_url`` is the server root
(``http://localhost:11434``)."""

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
    ToolCall,
    Usage,
)


def to_wire(m: Message) -> dict[str, Any]:
    out: dict[str, Any] = {"role": m.role, "content": m.content}
    if m.role == "tool":
        out["tool_name"] = m.name or ""
    if m.tool_calls:
        out["tool_calls"] = [
            {"function": {"name": c.name, "arguments": c.arguments or {}}} for c in m.tool_calls
        ]
    return out


def payload(req: ModelRequest) -> dict[str, Any]:
    options: dict[str, Any] = {"num_predict": req.max_tokens}
    if req.temperature is not None:
        options["temperature"] = req.temperature
    body: dict[str, Any] = {
        "model": req.model,
        "messages": [to_wire(m) for m in req.messages],
        "stream": False,
        "options": options,
    }
    if req.tools and req.tool_choice == "auto":
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
    return body


def _calls(msg: dict[str, Any], offset: int) -> list[ToolCall]:
    return [
        call(
            f"call_{offset + i}",
            (c.get("function") or {}).get("name", ""),
            (c.get("function") or {}).get("arguments"),
        )
        for i, c in enumerate(msg.get("tool_calls") or [])
    ]


def _usage(body: dict[str, Any]) -> Usage:
    return Usage(
        input_tokens=int(body.get("prompt_eval_count") or 0),
        output_tokens=int(body.get("eval_count") or 0),
    )


class OllamaAdapter(Adapter):
    def _headers(self) -> dict[str, str]:
        return {"authorization": f"Bearer {self.config.api_key}"} if self.config.api_key else {}

    async def list_models(self) -> list[str]:
        body = await self._get(f"{self.base}/api/tags", self._headers())
        return sorted(str(m.get("name")) for m in body.get("models") or [] if m.get("name"))

    async def complete(self, req: ModelRequest, on_delta: OnDelta | None = None) -> ModelResponse:
        body = await self._post(f"{self.base}/api/chat", payload(req), self._headers())
        msg = body.get("message") or {}
        calls = _calls(msg, 0)
        return ModelResponse(
            text=msg.get("content") or "",
            tool_calls=calls,
            usage=_usage(body),
            finish_reason="tool_calls"
            if calls
            else ("length" if body.get("done_reason") == "length" else "stop"),
            model=body.get("model") or req.model,
        )
