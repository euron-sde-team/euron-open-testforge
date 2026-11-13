"""Pull request diff scoping (A9)."""

from __future__ import annotations

from testforge.pulls.diff import Span, changed_ranges, scope

PATCH = """@@ -10,6 +10,8 @@ def a():
 context
-old line
+new line
+another
 context
@@ -40,3 +42,2 @@ def b():
 keep
-gone
 keep
\\ No newline at end of file"""


def test_changed_ranges_are_read_on_the_head_side() -> None:
    assert changed_ranges(PATCH) == [(11, 12), (43, 43)]
    assert changed_ranges(None) == []
    assert changed_ranges("@@ -0,0 +1,3 @@\n+a\n+b\n+c") == [(1, 3)]


def test_units_overlapping_a_change_are_in_scope() -> None:
    units = [
        Span("a", "app/x.py", 5, 11),
        Span("b", "app/x.py", 13, 30),
        Span("c", "app/x.py", 40, 50),
        Span("d", "app/new.py", 1, 3),
        Span("e", "app/old.py", 1, 3),
        Span("f", "app/untouched.py", 1, 100),
    ]
    changed = [
        {"path": "app/x.py", "status": "modified", "changed_lines": [[11, 12], [43, 43]]},
        {"path": "app/new.py", "status": "added", "changed_lines": []},
        {"path": "app/old.py", "status": "removed", "changed_lines": [[1, 3]]},
    ]
    assert scope(units, changed) == ["a", "c", "d"]
