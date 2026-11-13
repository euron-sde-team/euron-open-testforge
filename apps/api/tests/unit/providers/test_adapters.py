"""Each provider adapter translates the normalized messages to its wire format and back."""

from __future__ import annotations

from testforge.providers.adapters import anthropic, gemini, ollama, openai
from testforge.providers.adapters.base import parse_arguments
from testforge.providers.types import Message, ModelRequest, ToolCall, ToolSpec, classify_status

CALL = ToolCall(id="c1", name="lookup", arguments={"q": "x"}, raw_arguments='{"q": "x"}')
CONVO = (
    Message("system", "Be brief."),
    Message("user", "Find x"),
    Message("assistant", "", (CALL,)),
    Message("tool", "found", tool_call_id="c1", name="lookup"),
    Message("tool", "also", tool_call_id="c2", name="lookup"),
)
TOOLS = (
    ToolSpec(
        "lookup",
        "Look up",
        {
            "type": "object",
            "properties": {"q": {"type": "string"}},
            "additionalProperties": False,
            "$schema": "x",
        },
    ),
)


def test_openai_payload_and_parse() -> None:
    body = openai.payload(ModelRequest(model="m", messages=CONVO, tools=TOOLS, max_tokens=99))
    assert body["max_completion_tokens"] == 99 and body["stream"] is False
    assert body["messages"][2]["tool_calls"][0]["function"] == {
        "name": "lookup",
        "arguments": '{"q": "x"}',
    }
    assert body["messages"][2]["content"] is None
    assert body["messages"][3] == {"role": "tool", "tool_call_id": "c1", "content": "found"}
    out = openai.parse_response(
        {
            "model": "m-1",
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "prompt_tokens_details": {"cached_tokens": 4},
            },
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {"id": "a", "function": {"name": "lookup", "arguments": '{"q": 1}'}}
                        ],
                    },
                }
            ],
        }
    )
    assert (
        out.tool_calls[0].arguments == {"q": 1}
        and out.usage.cached_input_tokens == 4
        and out.text == ""
    )


def test_anthropic_merges_tool_results_into_one_user_turn() -> None:
    system, turns = anthropic.to_wire(CONVO)
    assert system == "Be brief."
    assert [t["role"] for t in turns] == ["user", "assistant", "user"]
    assert turns[1]["content"] == [
        {"type": "tool_use", "id": "c1", "name": "lookup", "input": {"q": "x"}}
    ]
    assert [b["tool_use_id"] for b in turns[2]["content"]] == ["c1", "c2"]
    out = anthropic.parse_response(
        {
            "content": [
                {"type": "text", "text": "hi"},
                {"type": "tool_use", "id": "t", "name": "lookup", "input": {}},
            ],
            "stop_reason": "tool_use",
            "usage": {"input_tokens": 3, "cache_read_input_tokens": 2, "output_tokens": 1},
        }
    )
    assert (
        out.finish_reason == "tool_calls"
        and out.usage.input_tokens == 5
        and out.usage.cached_input_tokens == 2
    )


def test_gemini_schema_is_reduced_and_roles_mapped() -> None:
    cleaned = gemini.clean_schema(
        {
            "type": "object",
            "additionalProperties": False,
            "$schema": "x",
            "properties": {"a": {"type": ["string", "null"], "default": "x"}},
        }
    )
    assert cleaned == {"type": "object", "properties": {"a": {"type": "string", "nullable": True}}}
    system, contents = gemini.to_wire(CONVO)
    assert system == "Be brief." and [c["role"] for c in contents] == ["user", "model", "user"]
    assert contents[2]["parts"][0] == {
        "functionResponse": {"name": "lookup", "response": {"content": "found"}}
    }


def test_ollama_payload() -> None:
    body = ollama.payload(
        ModelRequest(model="llama", messages=CONVO, tools=TOOLS, max_tokens=50, temperature=0.2)
    )
    assert body["options"] == {"num_predict": 50, "temperature": 0.2}
    assert body["messages"][3]["tool_name"] == "lookup"
    assert "tools" not in ollama.payload(
        ModelRequest(model="m", messages=CONVO, tools=TOOLS, tool_choice="none")
    )


def test_arguments_and_status_classification() -> None:
    assert parse_arguments('{"a": 1}') == {"a": 1}
    assert (
        parse_arguments("[1]") is None
        and parse_arguments("{bad") is None
        and parse_arguments("") == {}
    )
    assert classify_status(429) == (True, "rate_limited")
    assert classify_status(503)[0] is True and classify_status(401) == (False, "provider_auth")
    assert classify_status(400) == (False, "provider_rejected")


# The adapters over HTTP (a fake transport): requests, answers, errors.

import httpx  # noqa: E402
import pytest  # noqa: E402

from testforge.providers.adapters import adapter_for  # noqa: E402
from testforge.providers.adapters.base import ProviderConfig  # noqa: E402
from testforge.providers.types import ProviderError  # noqa: E402

ANSWERS = {
    "/v1/chat/completions": {
        "model": "m",
        "choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 1},
    },
    "/v1/models": {"data": [{"id": "b"}, {"id": "a"}]},
    "/v1/messages": {
        "model": "m",
        "content": [{"type": "text", "text": "hi"}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 3, "output_tokens": 1},
    },
    "/v1beta/models/m:generateContent": {
        "candidates": [{"content": {"parts": [{"text": "hi"}]}, "finishReason": "STOP"}],
        "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 1},
    },
    "/v1beta/models": {
        "models": [{"name": "models/m", "supportedGenerationMethods": ["generateContent"]}]
    },
    "/api/chat": {
        "model": "m",
        "message": {"content": "hi"},
        "done": True,
        "prompt_eval_count": 3,
        "eval_count": 1,
    },
    "/api/tags": {"models": [{"name": "m:7b"}]},
}


def _client(status: int = 200, seen: list[httpx.Request] | None = None) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        if status != 200:
            return httpx.Response(
                status, json={"error": {"message": "nope"}}, headers={"retry-after": "2"}
            )
        for path, body in ANSWERS.items():
            if request.url.path.endswith(path):
                return httpx.Response(200, json=body)
        return httpx.Response(404, json={"error": "unknown"})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


BASES = {
    "openai": "https://x/v1",
    "anthropic": "https://x",
    "gemini": "https://x",
    "ollama": "https://x",
}
REQ = ModelRequest(model="m", messages=(Message("system", "s"), Message("user", "q")))


@pytest.mark.parametrize("kind", list(BASES))
async def test_each_adapter_completes_and_lists_models(kind: str) -> None:
    seen: list[httpx.Request] = []
    async with _client(seen=seen) as http:
        adapter = adapter_for(
            ProviderConfig(kind, BASES[kind], api_key="k-1", headers={"x-team": "t"}), http
        )
        out = await adapter.complete(REQ)
        assert out.text == "hi" and out.usage.input_tokens == 3 and out.usage.output_tokens == 1
        models = await adapter.list_models()
        assert models and all(isinstance(m, str) for m in models)
    sent = seen[0]
    assert sent.headers["x-team"] == "t"
    assert "k-1" in " ".join(sent.headers.values())


@pytest.mark.parametrize(
    ("status", "code", "retryable"),
    [
        (429, "rate_limited", True),
        (503, "provider_unavailable", True),
        (401, "provider_auth", False),
    ],
)
async def test_errors_are_classified(status: int, code: str, retryable: bool) -> None:
    async with _client(status) as http:
        adapter = adapter_for(ProviderConfig("openai", "https://x/v1"), http)
        with pytest.raises(ProviderError) as caught:
            await adapter.complete(REQ)
    assert caught.value.code == code and caught.value.retryable is retryable
    assert "nope" in caught.value.message
    if retryable:
        assert caught.value.retry_after_s == 2.0


async def test_transport_failures_are_retryable() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    async with httpx.AsyncClient(transport=httpx.MockTransport(boom)) as http:
        adapter = adapter_for(ProviderConfig("anthropic", "https://x"), http)
        with pytest.raises(ProviderError) as caught:
            await adapter.complete(REQ)
    assert caught.value.code == "provider_unreachable" and caught.value.retryable
