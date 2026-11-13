"""Which lines a pull request changes, and which code units those lines touch.

GitHub returns each changed file with a unified diff patch between the pull request's base
and head. Line numbers are read on the head side: added lines are changed lines; a pure
deletion marks the head line where the removed text used to be, since the code around it
changed meaning. A unit is in scope when its line range (in the head commit's analysis)
overlaps a changed range of its file; every unit of an added file is in scope.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def changed_ranges(patch: str | None) -> list[tuple[int, int]]:
    """Head-side line ranges ``[(start, end), ...]`` (inclusive) a patch changes."""
    if not patch:
        return []
    lines: set[int] = set()
    new_line = 0
    for raw in patch.splitlines():
        m = HUNK.match(raw)
        if m:
            new_line = int(m.group(3))
            continue
        if not new_line:
            continue
        if raw.startswith("+"):
            lines.add(new_line)
            new_line += 1
        elif raw.startswith("-"):
            lines.add(max(new_line, 1))
        elif raw.startswith("\\"):
            continue  # "\ No newline at end of file"
        else:
            new_line += 1
    return _merge(sorted(lines))


def _merge(lines: list[int]) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for n in lines:
        if ranges and n <= ranges[-1][1] + 1:
            ranges[-1] = (ranges[-1][0], n)
        else:
            ranges.append((n, n))
    return ranges


@dataclass(frozen=True)
class Span:
    id: str
    file: str
    start: int
    end: int


def scope(units: Iterable[Span], changed: list[dict[str, object]]) -> list[str]:
    """Ids of the units the changed files touch."""
    by_file: dict[str, tuple[str, list[tuple[int, int]]]] = {}
    for f in changed:
        path = str(f["path"])
        raw = f.get("changed_lines") or []
        ranges = [(int(r[0]), int(r[1])) for r in raw] if isinstance(raw, list) else []
        by_file[path] = (str(f.get("status") or "modified"), ranges)
    out: list[str] = []
    for u in units:
        entry = by_file.get(u.file)
        if entry is None:
            continue
        status, ranges = entry
        if status == "removed":
            continue
        if status == "added" or any(a <= u.end and b >= u.start for a, b in ranges):
            out.append(u.id)
    return out
