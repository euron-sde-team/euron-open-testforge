"""Unpack an uploaded ZIP or a GitHub tarball into a normalized snapshot, defensively.

Nothing in an archive is trusted. Absolute paths, ``..``, symbolic and hard links, device
files and names with control characters are skipped; the entry count and the total
uncompressed size are capped while reading (a zip bomb stops at the cap, never after it);
dependency folders, virtualenvs, build output and binary files are left out because a run
never uses them. The result is an in-memory map of text files, and a ZIP of exactly those
files is what the snapshot stores.
"""

from __future__ import annotations

import io
import tarfile
import zipfile
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import IO

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    "dist",
    "build",
    ".next",
    "coverage",
    "htmlcov",
    ".testforge",
    ".idea",
    ".vscode",
}
SKIP_SUFFIXES = (".pyc", ".pyo", ".so", ".dll", ".dylib", ".exe", ".class", ".jar", ".lock")


class ArchiveError(Exception):
    """The archive cannot be read, or it is over a limit."""


@dataclass
class Snapshot:
    files: dict[str, str] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)
    size: int = 0

    def to_zip(self) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(self.files):
                zf.writestr(path, self.files[path])
        return buf.getvalue()


def clean_path(name: str) -> str | None:
    """A safe relative POSIX path, or None when the name must be skipped."""
    if not name or "\x00" in name or "\\" in name:
        return None
    if any(ord(c) < 32 for c in name):
        return None
    p = PurePosixPath(name)
    if p.is_absolute() or ".." in p.parts:
        return None
    parts = [x for x in p.parts if x not in ("", ".")]
    if not parts:
        return None
    return "/".join(parts)


def _keep(path: str) -> bool:
    parts = path.split("/")
    if any(part in SKIP_DIRS for part in parts[:-1]):
        return False
    return not path.endswith(SKIP_SUFFIXES)


def _strip_common_root(names: list[str]) -> str:
    """GitHub tarballs and many ZIPs wrap everything in one top folder; drop it."""
    tops = {n.split("/", 1)[0] for n in names}
    if len(tops) == 1 and all("/" in n for n in names):
        return next(iter(tops)) + "/"
    return ""


class _Budget:
    def __init__(self, max_files: int, max_bytes: int, max_file_bytes: int) -> None:
        self.max_files = max_files
        self.max_bytes = max_bytes
        self.max_file_bytes = max_file_bytes

    def add(self, snap: Snapshot, path: str, data: bytes) -> None:
        if len(data) > self.max_file_bytes:
            snap.skipped.append(f"{path} (larger than {self.max_file_bytes} bytes)")
            return
        if b"\x00" in data[:8192]:
            snap.skipped.append(f"{path} (binary)")
            return
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            snap.skipped.append(f"{path} (not UTF-8 text)")
            return
        if len(snap.files) >= self.max_files:
            raise ArchiveError(f"The archive has more than {self.max_files} files")
        snap.size += len(data)
        if snap.size > self.max_bytes:
            raise ArchiveError(f"The archive unpacks to more than {self.max_bytes} bytes")
        snap.files[path] = text


def _read_limited(fh: IO[bytes], limit: int) -> bytes:
    return fh.read(limit + 1)


def from_zip(data: bytes, *, max_files: int, max_bytes: int, max_file_bytes: int) -> Snapshot:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ArchiveError("The upload is not a valid ZIP file") from exc
    budget = _Budget(max_files, max_bytes, max_file_bytes)
    snap = Snapshot()
    with zf:
        infos = [i for i in zf.infolist() if not i.is_dir()]
        if len(infos) > max_files * 4:
            raise ArchiveError(f"The archive has more than {max_files * 4} entries")
        root = _strip_common_root([i.filename for i in infos])
        for info in infos:
            mode = (info.external_attr >> 16) & 0o170000
            if mode in (0o120000, 0o020000, 0o060000, 0o010000, 0o140000):
                snap.skipped.append(f"{info.filename} (link or device)")
                continue
            path = clean_path(info.filename[len(root) :] if root else info.filename)
            if path is None:
                snap.skipped.append(f"{info.filename} (unsafe name)")
                continue
            if not _keep(path):
                continue
            if info.file_size > max_file_bytes:
                snap.skipped.append(f"{path} (larger than {max_file_bytes} bytes)")
                continue
            with zf.open(info) as fh:
                # Read at most one byte past the cap: a lying header cannot inflate past it.
                content = _read_limited(fh, max_file_bytes)
            budget.add(snap, path, content)
    if not snap.files:
        raise ArchiveError("The archive contains no text files TestForge can read")
    return snap


def from_tarball(data: bytes, *, max_files: int, max_bytes: int, max_file_bytes: int) -> Snapshot:
    budget = _Budget(max_files, max_bytes, max_file_bytes)
    snap = Snapshot()
    try:
        tf = tarfile.open(fileobj=io.BytesIO(data), mode="r:*")  # noqa: SIM115 closed below
    except tarfile.TarError as exc:
        raise ArchiveError("The repository archive is not a valid tarball") from exc
    with tf:
        members: list[tarfile.TarInfo] = []
        for m in tf:
            if len(members) > max_files * 4:
                raise ArchiveError(f"The archive has more than {max_files * 4} entries")
            members.append(m)
        files = [m for m in members if m.isfile()]
        root = _strip_common_root([m.name for m in files])
        for m in members:
            if m.isdir():
                continue
            if not m.isfile():
                snap.skipped.append(f"{m.name} (link or device)")
                continue
            path = clean_path(m.name[len(root) :] if root else m.name)
            if path is None:
                snap.skipped.append(f"{m.name} (unsafe name)")
                continue
            if not _keep(path):
                continue
            if m.size > max_file_bytes:
                snap.skipped.append(f"{path} (larger than {max_file_bytes} bytes)")
                continue
            fh = tf.extractfile(m)
            if fh is None:
                continue
            budget.add(snap, path, _read_limited(fh, max_file_bytes))
    if not snap.files:
        raise ArchiveError("The repository contains no text files TestForge can read")
    return snap


def read_snapshot(data: bytes) -> dict[str, str]:
    """A stored snapshot (written by ``Snapshot.to_zip``) back into path -> text."""
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return {i.filename: zf.read(i).decode("utf-8") for i in zf.infolist() if not i.is_dir()}
