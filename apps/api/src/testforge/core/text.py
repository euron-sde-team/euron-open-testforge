"""Small text helpers shared by domains."""

from __future__ import annotations

import re


def slugify(text: str, fallback: str = "item") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60].strip("-")
    return slug or fallback


def excerpt(text: str, limit: int) -> str:
    """``text`` cut to ``limit`` characters, marking the cut."""
    if len(text) <= limit:
        return text
    return text[: max(limit - 40, 0)] + f"\n[... {len(text) - limit + 40:,} more characters]"
