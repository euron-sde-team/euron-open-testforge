"""A small GitHub REST API stand-in serving TestForge's demo projects as repositories, with
one pull request each, so imports, pull request scoping and webhooks are exercised against
a real HTTP server with no network and no token.

Repositories: ``euron-demo/python-shop`` and ``euron-demo/ts-toolkit`` (branch ``main``).
Pull requests: python-shop #12 (changes ``split_bill``, adds ``restock_plan``) and
ts-toolkit #4 (adds ``truncate``). The base of each pull request is the head with the
change taken back out, so the patches GitHub would return are computed, not hand-written.
A repository named ``euron-demo/private-*`` answers 404 without a bearer token.
"""

from __future__ import annotations

import difflib
import hashlib
import io
import tarfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

import testforge.demo

PROJECTS = Path(testforge.demo.__file__).parent / "projects"
router = APIRouter(prefix="/github")


@dataclass(frozen=True)
class Pull:
    number: int
    title: str
    author: str
    head_ref: str


SPLIT_BILL_BEFORE = '''def split_bill(total: float, people: int) -> list[float]:
    """Split a bill into equal shares.

    >>> split_bill(90.0, 3)
    [30.0, 30.0, 30.0]
    """
    return [round(total / people, 2)] * people
'''

RESTOCK = """

def restock_plan(levels: dict[str, int], target: int) -> dict[str, int]:"""


def _strip_after(text: str, marker: str) -> str:
    i = text.find(marker)
    return text if i == -1 else text[:i].rstrip() + "\n"


def _python_base(files: dict[str, str]) -> dict[str, str | None]:
    pricing = files["app/pricing.py"]
    start = pricing.index("def split_bill(")
    end = pricing.index("def format_price(")
    old_pricing = pricing[:start] + SPLIT_BILL_BEFORE + "\n\n" + pricing[end:]
    return {
        "app/pricing.py": old_pricing,
        "app/inventory.py": _strip_after(files["app/inventory.py"], RESTOCK.strip()),
    }


def _ts_base(files: dict[str, str]) -> dict[str, str | None]:
    slug = files["src/slug.ts"]
    return {"src/slug.ts": slug[: slug.index("/**\n * Shorten text")].rstrip() + "\n"}


REPOS: dict[str, tuple[str, Pull]] = {
    "euron-demo/python-shop": (
        "python-shop",
        Pull(12, "Plan restocks and split bills to the cent", "dev-ana", "restock-planning"),
    ),
    "euron-demo/ts-toolkit": (
        "ts-toolkit",
        Pull(4, "Add truncate() for card titles", "dev-ravi", "truncate-titles"),
    ),
}


@lru_cache
def files_of(project: str) -> dict[str, str]:
    root = PROJECTS / project
    return {
        str(p.relative_to(root)): p.read_text()
        for p in sorted(root.rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts and "node_modules" not in p.parts
    }


def _sha(files: dict[str, str | None]) -> str:
    h = hashlib.sha1(usedforsecurity=False)
    for path in sorted(files):
        h.update(path.encode() + b"\0" + (files[path] or "").encode() + b"\0")
    return h.hexdigest()


@lru_cache
def snapshots(repo: str) -> dict[str, dict[str, str]]:
    """{sha: files} for the head (main) and the pull request's base."""
    project, _ = REPOS[repo]
    head = files_of(project)
    changes = _python_base(head) if project == "python-shop" else _ts_base(head)
    base = {p: t for p, t in head.items() if p not in changes}
    base |= {p: t for p, t in changes.items() if t is not None}
    return {_sha(dict(head)): head, _sha(dict(base)): base}


def head_sha(repo: str) -> str:
    return next(iter(snapshots(repo)))


def base_sha(repo: str) -> str:
    return list(snapshots(repo))[1]


def _patch(before: str | None, after: str) -> str:
    lines = difflib.unified_diff((before or "").splitlines(), after.splitlines(), lineterm="", n=3)
    return "\n".join(line for line in lines if not line.startswith(("---", "+++")))


def _repo_or_404(owner: str, name: str, request: Request) -> str | JSONResponse:
    repo = f"{owner}/{name}"
    if name.startswith("private-") and not request.headers.get("authorization"):
        return JSONResponse({"message": "Not Found"}, status_code=404)
    if repo not in REPOS:
        return JSONResponse({"message": "Not Found"}, status_code=404)
    return repo


@router.get("/repos/{owner}/{name}")
async def repository(owner: str, name: str, request: Request) -> Any:
    repo = _repo_or_404(owner, name, request)
    if isinstance(repo, JSONResponse):
        return repo
    return {"full_name": repo, "default_branch": "main", "private": False}


@router.get("/repos/{owner}/{name}/commits/{ref:path}")
async def commit(owner: str, name: str, ref: str, request: Request) -> Any:
    repo = _repo_or_404(owner, name, request)
    if isinstance(repo, JSONResponse):
        return repo
    _, pull = REPOS[repo]
    if ref in ("main", pull.head_ref, head_sha(repo)):
        return {"sha": head_sha(repo)}
    if ref == base_sha(repo):
        return {"sha": ref}
    return JSONResponse({"message": "No commit found"}, status_code=404)


@router.get("/repos/{owner}/{name}/tarball/{sha}")
async def tarball(owner: str, name: str, sha: str, request: Request) -> Response:
    repo = _repo_or_404(owner, name, request)
    if isinstance(repo, JSONResponse):
        return repo
    files = snapshots(repo).get(sha)
    if files is None:
        return JSONResponse({"message": "Not Found"}, status_code=404)
    buf = io.BytesIO()
    top = f"{owner}-{name}-{sha[:7]}"
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for path, text in sorted(files.items()):
            data = text.encode()
            info = tarfile.TarInfo(f"{top}/{path}")
            info.size = len(data)
            info.mtime = 1_760_000_000
            tf.addfile(info, io.BytesIO(data))
    return Response(buf.getvalue(), media_type="application/x-gzip")


@router.get("/repos/{owner}/{name}/pulls/{number}")
async def pull_request(owner: str, name: str, number: int, request: Request) -> Any:
    repo = _repo_or_404(owner, name, request)
    if isinstance(repo, JSONResponse):
        return repo
    _, pull = REPOS[repo]
    if number != pull.number:
        return JSONResponse({"message": "Not Found"}, status_code=404)
    return {
        "number": pull.number,
        "title": pull.title,
        "state": "open",
        "user": {"login": pull.author},
        "base": {"ref": "main", "sha": base_sha(repo), "repo": {"full_name": repo}},
        "head": {"ref": pull.head_ref, "sha": head_sha(repo), "repo": {"full_name": repo}},
    }


@router.get("/repos/{owner}/{name}/pulls/{number}/files")
async def pull_files(owner: str, name: str, number: int, request: Request, page: int = 1) -> Any:
    repo = _repo_or_404(owner, name, request)
    if isinstance(repo, JSONResponse):
        return repo
    _, pull = REPOS[repo]
    if number != pull.number:
        return JSONResponse({"message": "Not Found"}, status_code=404)
    if page > 1:
        return []
    head = snapshots(repo)[head_sha(repo)]
    base = snapshots(repo)[base_sha(repo)]
    out = []
    for path in sorted(set(head) | set(base)):
        before, after = base.get(path), head.get(path)
        if before == after:
            continue
        patch = _patch(before, after or "")
        out.append(
            {
                "filename": path,
                "status": "added" if before is None else "removed" if after is None else "modified",
                "additions": sum(1 for x in patch.splitlines() if x.startswith("+")),
                "deletions": sum(1 for x in patch.splitlines() if x.startswith("-")),
                "patch": patch,
            }
        )
    return out
