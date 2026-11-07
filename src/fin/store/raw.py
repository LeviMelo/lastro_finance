"""L1 raw archive: immutable, content-addressed copies of everything fetched (PLAN §4.1 invariant 1, §4.2).

An object lives at `raw/<sha256[0:2]>/<sha256>.<ext>`. It is written once, through a temporary file in the same
directory and an atomic rename, and then marked read-only. Writing bytes that are already stored is a no-op that
verifies the stored size. Nothing in this module edits or deletes an object.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

_EXT = re.compile(r"^[a-z0-9]{1,12}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_CHUNK = 1 << 20


class RawStoreError(RuntimeError):
    """The archive disagrees with itself: a stored object's bytes do not hash to its name."""


@dataclass(frozen=True)
class RawRef:
    sha256: str
    ext: str
    size: int
    path: Path
    created: bool  # False when the object was already in the archive


def normalize_ext(ext: str) -> str:
    e = ext.lower().lstrip(".")
    if not _EXT.match(e):
        raise ValueError(f"raw extension must be 1-12 lowercase alphanumerics, got {ext!r}")
    return e


class RawStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def path_for(self, sha256: str, ext: str) -> Path:
        if not _SHA.match(sha256):
            raise ValueError(f"not a sha256 hex digest: {sha256!r}")
        return self.root / sha256[:2] / f"{sha256}.{normalize_ext(ext)}"

    def put_bytes(self, data: bytes, ext: str) -> RawRef:
        sha = hashlib.sha256(data).hexdigest()
        path = self.path_for(sha, ext)
        if path.exists():
            return self._existing(path, sha, ext, len(data))
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            return self._commit(Path(tmp), path, sha, ext, len(data))
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def put_stream(self, src: BinaryIO, ext: str) -> RawRef:
        """Store a stream (large downloads, owner inbox files) without holding it in memory."""
        self.root.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.root, prefix=".tmp-")
        h = hashlib.sha256()
        size = 0
        try:
            with os.fdopen(fd, "wb") as f:
                while chunk := src.read(_CHUNK):
                    h.update(chunk)
                    f.write(chunk)
                    size += len(chunk)
                f.flush()
                os.fsync(f.fileno())
            sha = h.hexdigest()
            path = self.path_for(sha, ext)
            if path.exists():
                Path(tmp).unlink()
                return self._existing(path, sha, ext, size)
            path.parent.mkdir(parents=True, exist_ok=True)
            return self._commit(Path(tmp), path, sha, ext, size)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def put_file(self, src: Path, ext: str | None = None) -> RawRef:
        with src.open("rb") as f:
            return self.put_stream(f, ext or src.suffix or "bin")

    def find(self, sha256: str) -> Path:
        if not _SHA.match(sha256):
            raise ValueError(f"not a sha256 hex digest: {sha256!r}")
        hits = sorted((self.root / sha256[:2]).glob(f"{sha256}.*"))
        if not hits:
            raise FileNotFoundError(f"raw object {sha256} is not in the archive")
        return hits[0]

    def read(self, sha256: str) -> bytes:
        return self.find(sha256).read_bytes()

    def verify(self, sha256: str) -> None:
        h = hashlib.sha256()
        with self.find(sha256).open("rb") as f:
            while chunk := f.read(_CHUNK):
                h.update(chunk)
        if h.hexdigest() != sha256:
            raise RawStoreError(f"raw object {sha256} hashes to {h.hexdigest()}")

    def iter_objects(self) -> Iterator[tuple[str, Path]]:
        if not self.root.exists():
            return
        for p in sorted(self.root.glob("??/*.*")):
            sha = p.name.split(".", 1)[0]
            if _SHA.match(sha):
                yield sha, p

    @staticmethod
    def _commit(tmp: Path, path: Path, sha: str, ext: str, size: int) -> RawRef:
        try:
            os.replace(tmp, path)
        except PermissionError:
            # Another writer committed the same object first (Windows refuses to replace a read-only file).
            tmp.unlink(missing_ok=True)
            if not path.exists():
                raise
            return RawRef(sha, normalize_ext(ext), size, path, created=False)
        os.chmod(path, stat.S_IREAD)
        return RawRef(sha, normalize_ext(ext), size, path, created=True)

    @staticmethod
    def _existing(path: Path, sha: str, ext: str, size: int) -> RawRef:
        stored = path.stat().st_size
        if stored != size:
            raise RawStoreError(f"raw object {sha} is stored with {stored} bytes, offered {size}")
        return RawRef(sha, normalize_ext(ext), size, path, created=False)
