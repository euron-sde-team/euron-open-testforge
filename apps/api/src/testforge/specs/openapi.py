"""Read an OpenAPI 3 document into the operations API tests are generated for."""

from __future__ import annotations

import json
from typing import Any

import yaml

from testforge.generation.templates import resolve

METHODS = ("get", "post", "put", "patch", "delete", "head", "options")


class SpecError(Exception):
    """The document is not an OpenAPI 3 document TestForge can read."""


def load(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except ValueError:
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise SpecError("The document is neither JSON nor YAML") from exc
    if not isinstance(data, dict):
        raise SpecError("The document is not an object")
    version = str(data.get("openapi", ""))
    if not version.startswith("3."):
        raise SpecError(
            "Only OpenAPI 3 documents are supported (the document has no openapi: 3.x field)"
        )
    if not isinstance(data.get("paths"), dict) or not data["paths"]:
        raise SpecError("The document has no paths")
    return data


def operations(doc: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path, item in doc.get("paths", {}).items():
        if not isinstance(item, dict):
            continue
        shared = [resolve(p, doc) for p in item.get("parameters", []) if isinstance(p, dict)]
        for method in METHODS:
            op = item.get(method)
            if not isinstance(op, dict):
                continue
            params = {(p.get("in"), p.get("name")): p for p in shared}
            for p in op.get("parameters", []):
                if isinstance(p, dict):
                    r = resolve(p, doc)
                    params[(r.get("in"), r.get("name"))] = r
            body = None
            rb = resolve(op.get("requestBody") or {}, doc)
            content = rb.get("content", {}) if isinstance(rb, dict) else {}
            if "application/json" in content:
                body = content["application/json"].get("schema", {})
            responses: dict[str, Any] = {}
            for code, resp in (op.get("responses") or {}).items():
                r = resolve(resp, doc) if isinstance(resp, dict) else {}
                schema = (r.get("content", {}).get("application/json") or {}).get("schema")
                responses[str(code)] = {"description": r.get("description", ""), "schema": schema}
            out.append(
                {
                    "key": f"{method.upper()} {path}",
                    "operation_id": op.get("operationId") or "",
                    "method": method.upper(),
                    "path": path,
                    "summary": op.get("summary") or op.get("description") or "",
                    "parameters": [
                        {
                            "name": p.get("name"),
                            "in": p.get("in"),
                            "required": bool(p.get("required")),
                            "schema": p.get("schema", {}),
                        }
                        for p in params.values()
                    ],
                    "request_body": body,
                    "responses": responses,
                }
            )
    return out
