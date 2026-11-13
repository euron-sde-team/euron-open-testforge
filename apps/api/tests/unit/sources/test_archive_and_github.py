"""Archives unpacked defensively, and GitHub repository names."""

from __future__ import annotations

import io
import tarfile
import zipfile

import pytest

from testforge.sources import archive
from testforge.sources.github import parse_repo

LIMITS = {"max_files": 50, "max_bytes": 100_000, "max_file_bytes": 10_000}


def _zip(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_zip_strips_the_common_root_and_skips_what_runs_never_use() -> None:
    snap = archive.from_zip(
        _zip(
            {
                "proj/app.py": b"x = 1\n",
                "proj/.git/config": b"[core]\n",
                "proj/node_modules/a/index.js": b"1",
                "proj/__pycache__/a.pyc": b"\x00",
                "proj/big.py": b"#" * 20_000,
                "proj/img.png": b"\x89PNG\x00\x00",
                "proj/latin.txt": "caf\xe9".encode("latin-1"),
            }
        ),
        **LIMITS,
    )
    assert set(snap.files) == {"app.py"}
    skipped = " ".join(snap.skipped)
    assert "larger than" in skipped and "binary" in skipped and "not UTF-8" in skipped
    assert archive.read_snapshot(snap.to_zip()) == {"app.py": "x = 1\n"}


def test_zip_limits() -> None:
    many = {f"f{i}.py": b"x\n" for i in range(60)}
    with pytest.raises(archive.ArchiveError, match="more than 50 files"):
        archive.from_zip(_zip(many), **LIMITS)
    big = {f"f{i}.py": b"#" * 9_000 for i in range(20)}
    with pytest.raises(archive.ArchiveError, match="unpacks to more than"):
        archive.from_zip(_zip(big), **LIMITS)
    with pytest.raises(archive.ArchiveError, match="not a valid ZIP"):
        archive.from_zip(b"nope", **LIMITS)
    with pytest.raises(archive.ArchiveError, match="no text files"):
        archive.from_zip(_zip({"a.png": b"\x00\x01"}), **LIMITS)


@pytest.mark.parametrize(
    ("name", "clean"),
    [
        ("a/b.py", "a/b.py"),
        ("./a/./b.py", "a/b.py"),
        ("../a.py", None),
        ("/etc/passwd", None),
        ("a\\b.py", None),
        ("a/\x01b.py", None),
        ("", None),
    ],
)
def test_clean_path(name: str, clean: str | None) -> None:
    assert archive.clean_path(name) == clean


def _tar(members: list[tarfile.TarInfo], data: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for m in members:
            tf.addfile(m, io.BytesIO(data[m.name]) if m.name in data else None)
    return buf.getvalue()


def test_tarball_skips_links_and_devices() -> None:
    f = tarfile.TarInfo("repo-abc/app.py")
    f.size = 6
    link = tarfile.TarInfo("repo-abc/link.py")
    link.type = tarfile.SYMTYPE
    link.linkname = "/etc/passwd"
    hard = tarfile.TarInfo("repo-abc/hard.py")
    hard.type = tarfile.LNKTYPE
    hard.linkname = "repo-abc/app.py"
    dev = tarfile.TarInfo("repo-abc/dev")
    dev.type = tarfile.CHRTYPE
    snap = archive.from_tarball(
        _tar([f, link, hard, dev], {"repo-abc/app.py": b"x = 1\n"}), **LIMITS
    )
    assert set(snap.files) == {"app.py"}
    assert sum("link or device" in s for s in snap.skipped) == 3
    with pytest.raises(archive.ArchiveError):
        archive.from_tarball(b"not a tarball", **LIMITS)


@pytest.mark.parametrize(
    ("value", "repo"),
    [
        ("euron-demo/python-shop", "euron-demo/python-shop"),
        ("https://github.com/euron-demo/python-shop.git", "euron-demo/python-shop"),
        ("https://github.com/euron-demo/python-shop/pull/12", "euron-demo/python-shop"),
    ],
)
def test_parse_repo(value: str, repo: str) -> None:
    assert parse_repo(value) == repo


@pytest.mark.parametrize(
    "value", ["", "x", "a/b/c", "a b/c", "https://github.com/x", "../etc/passwd"]
)
def test_parse_repo_refuses(value: str) -> None:
    with pytest.raises(ValueError):
        parse_repo(value)
