"""Google Gemini (generateContent). ``base_url`` is the API root
(``https://generativelanguage.googleapis.com``). Gemini function calls carry no ids, so the
adapter numbers them, and tool schemas are reduced to the OpenAPI subset Gemini accepts."""

from __future__ import annotations

import uuid
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
    ToolCall,
    Usage,
)

_SCHEMA_KEYS = {
    "type",
    "description",
    "properties",
    "required",
    "items",
    "enum",
    "format",
    "nullable",
    "minimum",
    "maximum",
    "minItems",
    "maxItems",
    "minLength",
    "maxLength",
    "anyOf",
}
_FINISH = {"STOP": "stop", "MAX_TOKENS": "length", "SAFETY": "content_filter"}


def clean_schema(schema: Any) -> Any:
    """Drop JSON Schema keywords Gemini refuses (additionalProperties, $schema, defaults)."""
    if isinstance(schema, list):
        return [clean_schema(s) for s in schema]
    if not isinstance(schema, dict):
        return schema
    out: dict[str, Any] = {}
    for key, value in schema.items():
        if key not in _SCHEMA_KEYS:
            continue
        if key == "properties" and isinstance(value, dict):
            out[key] = {name: clean_schema(sub) for name, sub in value.items()}
        elif key == "type" and isinstance(value, list):
            # ["string", "null"]: Gemini wants one type plus nullable.
            types = [t for t in value if t != "null"]
            out["type"] = types[0] if types else "string"
            if "null" in value:
                out["nullable"] = True
        else:
            out[key] = clean_schema(value)
    return out


def to_wire(messages: tuple[Message, ...]) -> tuple[str, list[dict[str, Any]]]:
    system = "\n\n".join(m.content for m in messages if m.role == "system" and m.content)
    contents: list[dict[str, Any]] = []
    for m in messages:
        if m.role == "system":
            continue
        if m.role == "tool":
            role = "user"
            parts: list[dict[str, Any]] = [
                {"functionResponse": {"name": m.name or "tool", "response": {"content": m.content}}}
            ]
        elif m.role == "assistant":
            role = "model"
            parts = [{"text": m.content}] if m.content else []
            parts += [
                {"functionCall": {"name": c.name, "args": c.arguments or {}}} for c in m.tool_calls
            ]
        else:
            role, parts = "user", [{"text": m.content}]
        if not parts:
            continue
        if contents and contents[-1]["role"] == role:
            contents[-1]["parts"].extend(parts)
        else:
            contents.append({"role": role, "parts": parts})
    return system, contents


def payload(req: ModelRequest) -> dict[str, Any]:
    system, contents = to_wire(req.messages)
    config: dict[str, Any] = {"maxOutputTokens": req.max_tokens}
    if req.temperature is not None:
        config["temperature"] = req.temperature
    body: dict[str, Any] = {"contents": contents, "generationConfig": config}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    if req.tools:
        body["tools"] = [
            {
                "functionDeclarations": [
                    {
                        "name": t.name,
                        "description": t.description,
                        "parameters": clean_schema(t.parameters),
                    }
                    for t in req.tools
                ]
            }
        ]
        body["toolConfig"] = {
            "functionCallingConfig": {"mode": "AUTO" if req.tool_choice == "auto" else "NONE"}
        }
    return body


def _usage(raw: dict[str, Any] | None) -> Usage:
    raw = raw or {}
    return Usage(
        input_tokens=int(raw.get("promptTokenCount") or 0),
        output_tokens=int(raw.get("candidatesTokenCount") or 0)
        + int(raw.get("thoughtsTokenCount") or 0),
        cached_input_tokens=int(raw.get("cachedContentTokenCount") or 0),
    )


def _calls_of(parts: list[dict[str, Any]]) -> list[ToolCall]:
    return [
        call(
            f"call_{uuid.uuid4().hex[:12]}",
            p["functionCall"].get("name", ""),
            p["functionCall"].get("args") or {},
        )
        for p in parts
        if "functionCall" in p
    ]


class GeminiAdapter(Adapter):
    def _headers(self) -> dict[str, str]:
        return {"x-goog-api-key": self.config.api_key} if self.config.api_key else {}

    async def list_models(self) -> list[str]:
        body = await self._get(f"{self.base}/v1beta/models?pageSize=1000", self._headers())
        return sorted(
            str(m.get("name", "")).removeprefix("models/")
            for m in body.get("models") or []
            if "generateContent" in (m.get("supportedGenerationMethods") or [])
        )

    async def complete(self, req: ModelRequest, on_delta: OnDelta | None = None) -> ModelResponse:
        model = req.model.removeprefix("models/")
        body = await self._post(
            f"{self.base}/v1beta/models/{model}:generateContent", payload(req), self._headers()
        )
        cands = body.get("candidates") or []
        if not cands:
            raise ProviderError("The provider returned no candidates", retryable=True)
        parts = (cands[0].get("content") or {}).get("parts") or []
        calls = _calls_of(parts)
        reason = cands[0].get("finishReason") or "STOP"
        return ModelResponse(
            text="".join(p.get("text", "") for p in parts if "text" in p and not p.get("thought")),
            tool_calls=calls,
            usage=_usage(body.get("usageMetadata")),
            finish_reason="tool_calls" if calls else _FINISH.get(reason, reason.lower()),
            model=body.get("modelVersion") or model,
        )
