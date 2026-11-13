"""Export the OpenAPI document. ``testforge openapi > docs/api/openapi.yaml``."""

from __future__ import annotations

from typing import Any

from testforge.core.config import Settings


def spec() -> dict[str, Any]:
    from testforge.main import create_app

    app = create_app(Settings())
    document: dict[str, Any] = app.openapi()
    document["servers"] = [{"url": "http://localhost:5430", "description": "Local (make up)"}]
    return document


def to_yaml(document: dict[str, Any]) -> str:
    import yaml

    return yaml.safe_dump(document, sort_keys=False, allow_unicode=True, width=100)
