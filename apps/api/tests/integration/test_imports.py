"""Imports and static analysis (A6), from ZIP uploads and the GitHub API."""

from __future__ import annotations

import io
import zipfile

import pytest

from tests.integration.conftest import Stack

pytestmark = pytest.mark.integration


async def test_python_project_is_analyzed(shop: Stack) -> None:
    """A6: language, framework, test framework, functions, classes, routes and gaps."""
    imports = await shop.ok("GET", shop.p("/imports"))
    imp = imports[0]
    assert imp["kind"] == "zip"
    assert imp["languages"] == ["python"]
    assert "fastapi" in imp["frameworks"]
    assert imp["test_frameworks"] == ["pytest"]
    assert imp["summary"]["test_files"] == ["tests/test_pricing.py"]
    assert imp["summary"]["apps"][0] == {
        "framework": "fastapi",
        "module": "app.main",
        "attr": "app",
        "file": "app/main.py",
    }
    units = await shop.ok("GET", shop.p(f"/imports/{imp['id']}/units"))
    by_name = {u["qualname"]: u for u in units}
    assert by_name["app.pricing.split_bill"]["kind"] == "function"
    assert by_name["app.cart.Cart"]["kind"] == "class"
    assert by_name["app.cart.Cart.add"]["kind"] == "method"
    assert by_name["GET /products/{product_id}"]["kind"] == "route"
    raises = by_name["app.inventory.reserve"]["details"]["raises"]
    assert {r["condition"] for r in raises} == {"quantity <= 0", "quantity > stock"}
    # The project's own test refers to apply_discount only: everything else is a gap.
    assert by_name["app.pricing.apply_discount"]["referenced_by_tests"] is True
    analysis = await shop.ok("GET", shop.p("/analysis"))
    untested = {u["qualname"] for u in analysis["untested_units"]}
    assert "app.pricing.split_bill" in untested
    assert "app.pricing.apply_discount" not in untested
    assert analysis["untested"] == len(untested)


async def test_typescript_project_is_analyzed(ready: Stack) -> None:
    imp = await ready.import_zip("ts-toolkit")
    assert imp["status"] == "ready", imp
    assert imp["languages"] == ["typescript"]
    assert imp["test_frameworks"] == ["vitest"]
    units = await ready.ok("GET", ready.p(f"/imports/{imp['id']}/units"))
    kinds = {u["qualname"]: u["kind"] for u in units}
    assert kinds["src/money.formatPrice"] == "function"
    assert kinds["src/money.addTip"] == "function"
    assert kinds["src/basket.Basket"] == "class"
    assert kinds["src/basket.Basket.count"] == "method"
    assert kinds["GET /health"] == "route"
    clamp = next(u for u in units if u["name"] == "clamp")
    assert clamp["details"]["examples"][0] == {
        "setup": [],
        "expression": "clamp(15, 0, 10)",
        "expected": "10",
    }
    assert clamp["details"]["raises"][0]["exception"] == "RangeError"


async def test_files_and_file_view(shop: Stack) -> None:
    imp = (await shop.ok("GET", shop.p("/imports")))[0]
    files = await shop.ok("GET", shop.p(f"/imports/{imp['id']}/files"))
    assert {"path": "app/pricing.py", "language": "python"}.items() <= next(
        f for f in files if f["path"] == "app/pricing.py"
    ).items()
    view = await shop.ok(
        "GET", shop.p(f"/imports/{imp['id']}/file"), params={"path": "app/pricing.py"}
    )
    assert "def split_bill" in view["content"]
    assert {u["name"] for u in view["units"]} >= {"split_bill", "apply_discount"}
    missing = await shop.client.get(
        shop.p(f"/imports/{imp['id']}/file"), params={"path": "../../etc/passwd"}
    )
    assert missing.status_code == 404


async def test_github_repository_import(ready: Stack) -> None:
    imp = await ready.import_github("euron-demo/python-shop")
    assert imp["status"] == "ready", imp
    assert imp["kind"] == "github"
    assert imp["ref"] == "main"
    assert len(imp["commit_sha"]) == 40
    assert "fastapi" in imp["frameworks"]
    project = await ready.ok("GET", ready.p())
    assert project["github_repo"] == "euron-demo/python-shop"
    assert project["current_import_id"] == imp["id"]


async def test_github_errors_are_explained(ready: Stack) -> None:
    imp = await ready.import_github("euron-demo/private-thing")
    assert imp["status"] == "failed"
    assert "private" in imp["error"] or "no such repository" in imp["error"]
    bad = await ready.client.post(ready.p("/imports/github"), json={"repo": "not a repo"})
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "invalid_repo"


def _zip(entries: dict[str, bytes], *, symlink: str | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
        if symlink:
            info = zipfile.ZipInfo(symlink)
            info.external_attr = (0o120777 << 16)
            zf.writestr(info, "/etc/passwd")
    return buf.getvalue()


async def test_unsafe_archive_entries_are_skipped(ready: Stack) -> None:
    data = _zip(
        {
            "proj/app.py": b"def ok():\n    return 1\n",
            "../escape.py": b"x = 1\n",
            "/abs/path.py": b"x = 1\n",
            "proj/node_modules/lib/index.js": b"module.exports = 1\n",
            "proj/blob.bin": b"\x00\x01\x02" * 100,
        },
        symlink="proj/link.py",
    )
    resp = await ready.client.post(
        ready.p("/imports/zip"), params={"wait": 60}, files={"file": ("p.zip", data, "application/zip")}
    )
    imp = resp.json()
    assert imp["status"] == "ready", imp
    files = await ready.ok("GET", ready.p(f"/imports/{imp['id']}/files"))
    assert [f["path"] for f in files] == ["proj/app.py"] or [f["path"] for f in files] == ["app.py"]
    skipped = " ".join(imp["summary"]["skipped"])
    assert "unsafe name" in skipped
    assert "link or device" in skipped
    assert "binary" in skipped


async def test_zip_bomb_is_stopped_at_the_cap(stack: Stack) -> None:
    stack.settings.max_snapshot_bytes = 200_000  # the API and worker share this object
    await stack.project()
    await stack.provider()
    big = {f"p/f{i}.py": (b"# " + b"x" * 60_000 + b"\n") for i in range(10)}
    resp = await stack.client.post(
        stack.p("/imports/zip"), params={"wait": 60}, files={"file": ("b.zip", _zip(big), "application/zip")}
    )
    imp = resp.json()
    assert imp["status"] == "failed"
    assert "unpacks to more than" in imp["error"]


async def test_not_a_zip(ready: Stack) -> None:
    resp = await ready.client.post(
        ready.p("/imports/zip"), files={"file": ("x.zip", b"hello", "application/zip")}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "not_a_zip"
