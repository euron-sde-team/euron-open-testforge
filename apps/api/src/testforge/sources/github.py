"""The GitHub REST API, read only: a repository's archive, a pull request and its files.

Nothing is cloned and no git hook or build step ever runs: the repository arrives as the
tarball GitHub serves for one commit and is unpacked by ``archive.py``. Requests go only
to GITHUB_API_URL (github.com's API unless configured otherwise); redirects are followed
only to GitHub's own archive host (codeload), never anywhere a repository name chose.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

REPO = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}$")
REF = re.compile(r"^[A-Za-z0-9._/-]{1,200}$")
ARCHIVE_HOSTS = {"codeload.github.com"}


class GitHubError(Exception):
    def __init__(
        self, message: str, *, status: int | None = None, code: str = "github_error"
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code


def parse_repo(value: str) -> str:
    """``owner/name`` from ``owner/name``, ``https://github.com/owner/name(.git)`` or a
    pull request URL. Raises ValueError for anything else."""
    text = value.strip()
    if "://" in text:
        parts = [p for p in urlsplit(text).path.split("/") if p]
        if len(parts) < 2:
            raise ValueError("a GitHub repository is owner/name")
        text = f"{parts[0]}/{parts[1]}"
    text = text.removesuffix(".git")
    if not REPO.match(text):
        raise ValueError("a GitHub repository is owner/name (letters, digits, dots, dashes)")
    return text


@dataclass
class PullRequest:
    number: int
    title: str
    author: str
    base_ref: str
    base_sha: str
    head_ref: str
    head_sha: str
    head_repo: str


@dataclass
class ChangedFile:
    path: str
    status: str
    additions: int
    deletions: int
    patch: str | None
    previous_path: str | None = None


class GitHub:
    def __init__(
        self, http: httpx.AsyncClient, api_url: str, token: str | None, timeout_s: float
    ) -> None:
        self.http = http
        self.base = api_url.rstrip("/")
        self.token = token
        self.timeout = timeout_s

    def _headers(self) -> dict[str, str]:
        h = {
            "accept": "application/vnd.github+json",
            "x-github-api-version": "2022-11-28",
            "user-agent": "euron-open-testforge",
        }
        if self.token:
            h["authorization"] = f"Bearer {self.token}"
        return h

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        try:
            resp = await self.http.get(
                f"{self.base}{path}", headers=self._headers(), params=params, timeout=self.timeout
            )
        except httpx.HTTPError as exc:
            raise GitHubError(
                f"GitHub could not be reached ({exc.__class__.__name__})", code="github_unreachable"
            ) from exc
        self._raise(resp)
        return resp.json()

    @staticmethod
    def _raise(resp: httpx.Response) -> None:
        if resp.status_code < 400:
            return
        if resp.status_code in (401, 403):
            raise GitHubError(
                "GitHub refused the request: the repository is private or the token lacks "
                "access. Add a token with read access to contents and pull requests",
                status=resp.status_code,
                code="github_forbidden",
            )
        if resp.status_code == 404:
            raise GitHubError(
                "GitHub has no such repository, ref or pull request "
                "(or it is private: add a token)",
                status=404,
                code="github_not_found",
            )
        raise GitHubError(f"GitHub answered {resp.status_code}", status=resp.status_code)

    async def default_branch(self, repo: str) -> str:
        data = await self._get(f"/repos/{repo}")
        return str(data.get("default_branch") or "main")

    async def commit_sha(self, repo: str, ref: str) -> str:
        if not REF.match(ref):
            raise GitHubError("That is not a valid branch, tag or commit", code="github_bad_ref")
        data = await self._get(f"/repos/{repo}/commits/{ref}")
        return str(data["sha"])

    async def tarball(self, repo: str, sha: str, max_bytes: int) -> bytes:
        """The repository at ``sha`` as a gzipped tarball, read up to ``max_bytes``."""
        url = f"{self.base}/repos/{repo}/tarball/{sha}"
        for _ in range(3):
            try:
                async with self.http.stream(
                    "GET", url, headers=self._headers(), timeout=self.timeout
                ) as resp:
                    if resp.status_code in (301, 302, 307, 308):
                        location = resp.headers.get("location", "")
                        host = urlsplit(location).hostname or ""
                        same = urlsplit(location).netloc == urlsplit(self.base).netloc
                        if not (host in ARCHIVE_HOSTS or same) or not location.startswith(
                            ("https://", "http://")
                        ):
                            raise GitHubError("GitHub redirected the archive somewhere unexpected")
                        url = location
                        continue
                    self._raise(resp)
                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in resp.aiter_bytes(1 << 16):
                        size += len(chunk)
                        if size > max_bytes:
                            raise GitHubError(
                                f"The repository archive is larger than {max_bytes} bytes",
                                code="github_too_large",
                            )
                        chunks.append(chunk)
                    return b"".join(chunks)
            except httpx.HTTPError as exc:
                raise GitHubError(
                    f"GitHub could not be reached ({exc.__class__.__name__})",
                    code="github_unreachable",
                ) from exc
        raise GitHubError("GitHub redirected the archive too many times")

    async def pull_request(self, repo: str, number: int) -> PullRequest:
        d = await self._get(f"/repos/{repo}/pulls/{number}")
        return PullRequest(
            number=int(d["number"]),
            title=str(d.get("title") or ""),
            author=str((d.get("user") or {}).get("login") or ""),
            base_ref=str(d["base"]["ref"]),
            base_sha=str(d["base"]["sha"]),
            head_ref=str(d["head"]["ref"]),
            head_sha=str(d["head"]["sha"]),
            head_repo=str(((d["head"].get("repo") or {}).get("full_name")) or repo),
        )

    async def pull_files(self, repo: str, number: int, limit: int = 3000) -> list[ChangedFile]:
        out: list[ChangedFile] = []
        page = 1
        while len(out) < limit:
            batch = await self._get(
                f"/repos/{repo}/pulls/{number}/files", params={"per_page": 100, "page": page}
            )
            if not isinstance(batch, list) or not batch:
                break
            for f in batch:
                out.append(
                    ChangedFile(
                        path=str(f["filename"]),
                        status=str(f.get("status") or "modified"),
                        additions=int(f.get("additions") or 0),
                        deletions=int(f.get("deletions") or 0),
                        patch=f.get("patch"),
                        previous_path=f.get("previous_filename"),
                    )
                )
            if len(batch) < 100:
                break
            page += 1
        return out
