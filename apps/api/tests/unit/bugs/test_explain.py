"""Failure explanations from captured values (A8)."""

from __future__ import annotations

from testforge.bugs.explain import explain


def test_a_list_comparison_names_the_difference() -> None:
    case = {
        "name": "test_split_bill_example_2",
        "file": "tests/testforge/test_split.py",
        "failure": {
            "message": "AssertionError: assert [33.33, 33.33, 33.33] == [33.34, 33.33, 33.33]",
            "path": "tests/testforge/test_split.py",
            "line": 11,
            "compare": {
                "operator": "==",
                "left": "[33.33, 33.33, 33.33]",
                "right": "[33.34, 33.33, 33.33]",
            },
        },
    }
    out = explain(case, "    assert split_bill(100.0, 3) == [33.34, 33.33, 33.33]")
    assert out["kind"] == "assertion"
    assert out["actual"] == "[33.33, 33.33, 33.33]" and out["expected"] == "[33.34, 33.33, 33.33]"
    assert out["expression"] == "assert split_bill(100.0, 3) == [33.34, 33.33, 33.33]"
    assert "first differ at index 0: 33.33 instead of 33.34" in out["explanation"]
    assert "add up to 99.99 instead of 100.0" in out["explanation"]
    assert "tests/testforge/test_split.py:11" in out["explanation"]


def test_numbers_dicts_and_lengths() -> None:
    num = explain(
        {"name": "t", "failure": {"compare": {"left": "16.99", "right": "17.0", "operator": "=="}}}
    )
    assert "difference is -0.01" in num["explanation"]
    d = explain(
        {
            "name": "t",
            "failure": {
                "compare": {
                    "left": "{'a': 1, 'b': 2}",
                    "right": "{'a': 2, 'c': 3}",
                    "operator": "==",
                }
            },
        }
    )
    assert "missing keys ['c']" in d["explanation"] and "unexpected keys ['b']" in d["explanation"]
    lists = explain(
        {"name": "t", "failure": {"compare": {"left": "[1]", "right": "[1, 2]", "operator": "=="}}}
    )
    assert "has 1 items where 2 were expected" in lists["explanation"]
    js = explain({"name": "t", "failure": {"compare": {"left": "0", "right": "3", "operator": ""}}})
    assert "returned 0" in js["explanation"]
    opaque = explain(
        {
            "name": "t",
            "failure": {"compare": {"left": "<Obj>", "right": "<Other>", "operator": ">"}},
        }
    )
    assert "to be greater than" in opaque["explanation"]


def test_missing_exception_and_errors() -> None:
    raised = explain(
        {"name": "t", "failure": {"message": "Failed: DID NOT RAISE <class 'ValueError'>"}}
    )
    assert raised["kind"] == "no_exception" and raised["expected"] == "ValueError"
    js = explain(
        {
            "name": "t",
            "failure": {"message": "AssertionError: expected [Function] to throw an error"},
        }
    )
    assert js["kind"] == "no_exception"
    error = explain({"name": "t", "failure": {"message": "ZeroDivisionError: division by zero"}})
    assert error["kind"] == "error" and "before it could check anything" in error["explanation"]
    plain = explain({"name": "t", "failure": {"message": "AssertionError: boom"}})
    assert plain["kind"] == "assertion"
    empty = explain({"name": "t"})
    assert empty["kind"] == "error"


def test_refused_network_and_file_access_are_named() -> None:
    net = explain(
        {"name": "t", "failure": {"message": "OSError: [Errno 101] Network is unreachable"}}
    )
    assert net["kind"] == "refused" and "refused it" in net["explanation"]
    dns = explain(
        {
            "name": "t",
            "failure": {
                "message": "socket.gaierror: [Errno -3] Temporary failure in name resolution"
            },
        }
    )
    assert dns["kind"] == "refused"
    host = explain(
        {
            "name": "t",
            "failure": {
                "message": "FileNotFoundError: [Errno 2] No such file or directory: '/etc/passwd'"
            },
        }
    )
    assert host["kind"] == "refused" and "outside its workspace" in host["explanation"]
    own = explain(
        {
            "name": "t",
            "failure": {
                "message": "FileNotFoundError: [Errno 2] No such file or directory: '/box/data.csv'"
            },
        }
    )
    assert own["kind"] == "error"
