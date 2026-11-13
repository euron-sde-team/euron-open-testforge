"""The normalized model interface every provider adapter speaks.

TestForge never sees a vendor wire format: messages and usage are translated at the
adapter boundary, so test generation and failure explanations work the same for every
provider. (The adapters also translate tool definitions and calls.)
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

Role = Literal["system", "user", "assistant", "tool"]


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    # Parsed arguments; ``None`` when the model sent text that is not a JSON object
    # (``raw_arguments`` keeps it so the error can be shown to the model).
    arguments: dict[str, Any] | None
    raw_arguments: str = ""


@dataclass(frozen=True, slots=True)
class Message:
    role: Role
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    # For role "tool": the call this answers, and the tool's name.
    tool_call_id: str | None = None
    name: str | None = None


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ModelRequest:
    model: str
    messages: tuple[Message, ...]
    tools: tuple[ToolSpec, ...] = ()
    max_tokens: int = 1024
    temperature: float | None = None
    # "auto" lets the model choose; "none" forbids tools for this call.
    tool_choice: Literal["auto", "none"] = "auto"


@dataclass(slots=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    # Prompt tokens the provider served from its cache (billed differently by some).
    cached_input_tokens: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(slots=True)
class ModelResponse:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    # "stop", "tool_calls", "length", "content_filter" or the provider's own word.
    finish_reason: str = "stop"
    # The model id the provider reports (it may resolve an alias).
    model: str = ""
    # True when the usage numbers came from the provider, False when estimated.
    usage_reported: bool = True


# A callback for text as it is produced (the mock calls it once with the whole answer).
OnDelta = Callable[[str], Awaitable[None]]


class ProviderError(Exception):
    """A failed model call. ``retryable`` errors (rate limits, overload, timeouts, 5xx)
    are retried by the retry manager; the others fail the step at once."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        retryable: bool = False,
        retry_after_s: float | None = None,
        code: str = "provider_error",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.retryable = retryable
        self.retry_after_s = retry_after_s
        self.code = code


def classify_status(status: int) -> tuple[bool, str]:
    """Whether an HTTP status from a provider is worth retrying, and an error code."""
    if status == 429:
        return True, "rate_limited"
    if status in (408, 409, 425) or status >= 500:
        return True, "provider_unavailable"
    if status in (401, 403):
        return False, "provider_auth"
    if status == 404:
        return False, "model_not_found"
    return False, "provider_rejected"
