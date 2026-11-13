"""Errors the SDK raises."""

from __future__ import annotations

from typing import Any


class TestForgeError(Exception):
    """The API answered with an error: ``status``, a machine-readable ``code`` and a message
    written for people."""

    __test__ = False

    def __init__(
        self, status: int, code: str, message: str, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(f"{status} {code}: {message}")
        self.status = status
        self.code = code
        self.message = message
        self.details = details or {}
