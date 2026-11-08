"""L1 raw archive: immutable, content-addressed copies of everything fetched (PLAN §4.1 invariant 1, §4.2).

An object is named by the SHA-256 of its **original bytes** and lives at `raw/<sha256[0:2]>/<sha256>.<ext>`. Text
payloads of 64 KiB or more (csv, txt, json, xml, html) are kept zstd-compressed at rest as `<sha256>.<ext>.zst`
(ADR-0009): `read` returns the original bytes exactly, and `verify` hashes those. It is written once, through a
temporary file in the same directory and an atomic rename, and then marked read-only. Writing bytes that are already
stored is a no-op that verifies the stored size.

**Deltas (ADR-0014).** A file a source re-sends with small changes (a full history re-uploaded daily, a registry, a
weekly zip) is stored as `<sha256>.<ext>.zsd`: a header naming its base object, then a zstd frame compressed with the
base's bytes as dictionary. It is kept only when it is under half the plain encoding, chains are cut by a full
keyframe every `KEYFRAME` versions, and the original bytes are rebuilt and hashed before the object is committed.
`rewrite_as_delta` re-encodes an object already stored (same original bytes, verified, then the old encoding is
removed): the only operation that touches a stored file, and it never changes what `read` returns.
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

import zstandard

_EXT = re.compile(r"^[a-z0-9]{1,12}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_CHUNK = 1 << 20
# szip: a zip written uncompressed (ZIP_STORED) to hold several members verbatim, so zstd compresses them (cvm_rad)
COMPRESSIBLE = frozenset({"csv", "txt", "json", "xml", "html", "tsv", "szip"})
COMPRESS_FROM = 64 * 1024
_LEVEL = 9
DELTA_FROM = 16 * 1024  # smaller objects are not worth a chain
KEYFRAME = 16  # a delta chain is at most this long; the next version is stored whole
_DELTA_MAGIC = b"LASTRO-ZSD1 "
_DELTA_HEAD = len(_DELTA_MAGIC) + 64 + 1 + 3 + 1  # magic, base sha, space, depth (3 digits), newline
_WINDOW_LOG = 28  # 256 MiB: the largest re-sent payloads (CVM members up to ~220 MB, B3 registries ~25 MB) fit


class RawStoreError(RuntimeError):
    """The archive disagrees with itself: a stored object's bytes do not hash to its name."""


@dataclass(frozen=True)
class RawRef:
    sha256: str
    ext: str
    size: int  # of the original bytes
    path: Path
    created: bool  # False when the object was already in the archive


def normalize_ext(ext: str) -> str:
    e = ext.lower().lstrip(".")
    if not _EXT.match(e):
        raise ValueError(f"raw extension must be 1-12 lowercase alphanumerics, got {ext!r}")
    return e


def _compressed(ext: str, size: int) -> bool:
    return ext in COMPRESSIBLE and size >= COMPRESS_FROM


class RawStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self._cache: dict[str, bytes] = {}  # the last few rebuilt objects: reading a chain in order stays linear

    def path_for(self, sha256: str, ext: str, size: int) -> Path:
        if not _SHA.match(sha256):
            raise ValueError(f"not a sha256 hex digest: {sha256!r}")
        e = normalize_ext(ext)
        name = f"{sha256}.{e}.zst" if _compressed(e, size) else f"{sha256}.{e}"
        return self.root / sha256[:2] / name

    def put_bytes(self, data: bytes, ext: str, base: str | None = None) -> RawRef:
        """Store `data`. With `base` (the previous version of the same file), store a delta when it pays."""
        sha = hashlib.sha256(data).hexdigest()
        held = self._held(sha)
        if held is not None:
            return self._existing(held, sha, ext, len(data))
        if base is not None and base != sha:
            ref = self._put_delta(data, sha, ext, base)
            if ref is not None:
                return ref
        path = self.path_for(sha, ext, len(data))
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as f:
                if path.suffix == ".zst":
                    f.write(zstandard.ZstdCompressor(level=_LEVEL, write_content_size=True).compress(data))
                else:
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
            held = self._held(sha)
            if held is not None:
                Path(tmp).unlink()
                return self._existing(held, sha, ext, size)
            path = self.path_for(sha, ext, size)
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.suffix == ".zst":
                fd2, tmp2 = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
                with open(tmp, "rb") as fin, os.fdopen(fd2, "wb") as fout:
                    zstandard.ZstdCompressor(level=_LEVEL, write_content_size=True).copy_stream(fin, fout, size=size)
                    fout.flush()
                    os.fsync(fout.fileno())
                Path(tmp).unlink()
                tmp = tmp2
            return self._commit(Path(tmp), path, sha, ext, size)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def put_file(self, src: Path, ext: str | None = None) -> RawRef:
        with src.open("rb") as f:
            return self.put_stream(f, ext or src.suffix or "bin")

    def _held(self, sha256: str) -> Path | None:
        hits = sorted((self.root / sha256[:2]).glob(f"{sha256}.*"))
        hits = [p for p in hits if not p.name.startswith(".tmp-")]
        return hits[0] if hits else None

    def find(self, sha256: str) -> Path:
        if not _SHA.match(sha256):
            raise ValueError(f"not a sha256 hex digest: {sha256!r}")
        held = self._held(sha256)
        if held is None:
            raise FileNotFoundError(f"raw object {sha256} is not in the archive")
        return held

    def read(self, sha256: str) -> bytes:
        if sha256 in self._cache:
            return self._cache[sha256]
        path = self.find(sha256)
        if path.suffix == ".zsd":
            data = self._read_delta(path)
        elif path.suffix == ".zst":
            with path.open("rb") as f:
                data = zstandard.ZstdDecompressor().stream_reader(f).read()
        else:
            data = path.read_bytes()
        self._remember(sha256, data)
        return data

    def open(self, sha256: str) -> BinaryIO:
        """A stream of the original bytes (for payloads too large to hold in memory)."""
        path = self.find(sha256)
        if path.suffix == ".zsd":
            import io

            return io.BytesIO(self.read(sha256))
        f = path.open("rb")
        if path.suffix == ".zst":
            return zstandard.ZstdDecompressor().stream_reader(f, closefd=True)  # type: ignore[return-value]
        return f

    def verify(self, sha256: str, path: Path | None = None) -> None:
        if path is not None and path.suffix == ".zsd":
            data = self._read_delta(path)
            if hashlib.sha256(data).hexdigest() != sha256:
                raise RawStoreError(f"raw object {sha256}: the delta {path.name} does not rebuild it")
            return
        h = hashlib.sha256()
        with self.open(sha256) as f:
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

    # ------------------------------------------------------------------------------------------- deltas

    def depth(self, sha256: str) -> int:
        """0 for an object stored whole, else the length of its delta chain."""
        path = self.find(sha256)
        if path.suffix != ".zsd":
            return 0
        return self._header(path)[1]

    def base_of(self, sha256: str) -> str | None:
        path = self.find(sha256)
        return self._header(path)[0] if path.suffix == ".zsd" else None

    def stored_size(self, sha256: str) -> int:
        return self.find(sha256).stat().st_size

    def _remember(self, sha: str, data: bytes) -> None:
        self._cache[sha] = data
        while len(self._cache) > 3:
            self._cache.pop(next(iter(self._cache)))

    @staticmethod
    def _header(path: Path) -> tuple[str, int, int]:
        with path.open("rb") as f:
            head = f.read(_DELTA_HEAD)
        if not head.startswith(_DELTA_MAGIC) or len(head) != _DELTA_HEAD:
            raise RawStoreError(f"{path.name}: not a LASTRO delta object")
        rest = head[len(_DELTA_MAGIC) :].decode("ascii")
        base, depth = rest[:64], int(rest[65:68])
        return base, depth, _DELTA_HEAD

    def _read_delta(self, path: Path) -> bytes:
        base, _, offset = self._header(path)
        dictionary = zstandard.ZstdCompressionDict(self.read(base), dict_type=zstandard.DICT_TYPE_RAWCONTENT)
        frame = path.read_bytes()[offset:]
        return zstandard.ZstdDecompressor(dict_data=dictionary, max_window_size=1 << _WINDOW_LOG).decompress(frame)

    def _encode_delta(self, data: bytes, base: str) -> tuple[bytes, int] | None:
        """(stored bytes, depth) of `data` as a delta of `base`, or None when a delta does not pay."""
        if len(data) < DELTA_FROM or self._held(base) is None:
            return None
        depth = self.depth(base) + 1
        if depth > KEYFRAME or depth > 999:
            return None
        base_bytes = self.read(base)
        dictionary = zstandard.ZstdCompressionDict(base_bytes, dict_type=zstandard.DICT_TYPE_RAWCONTENT)
        params = zstandard.ZstdCompressionParameters.from_level(
            _LEVEL, window_log=_WINDOW_LOG, enable_ldm=True, write_content_size=True
        )
        frame = zstandard.ZstdCompressor(dict_data=dictionary, compression_params=params).compress(data)
        plain = len(zstandard.ZstdCompressor(level=3).compress(data))
        if len(frame) * 2 > plain:
            return None
        head = _DELTA_MAGIC + f"{base} {depth:03d}\n".encode("ascii")
        assert len(head) == _DELTA_HEAD
        rebuilt = zstandard.ZstdDecompressor(dict_data=dictionary, max_window_size=1 << _WINDOW_LOG).decompress(frame)
        if hashlib.sha256(rebuilt).hexdigest() != hashlib.sha256(data).hexdigest():
            raise RawStoreError("a delta did not rebuild its original bytes")  # never stored
        return head + frame, depth

    def _put_delta(self, data: bytes, sha: str, ext: str, base: str) -> RawRef | None:
        enc = self._encode_delta(data, base)
        if enc is None:
            return None
        path = self.root / sha[:2] / f"{sha}.{normalize_ext(ext)}.zsd"
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(enc[0])
                f.flush()
                os.fsync(f.fileno())
            ref = self._commit(Path(tmp), path, sha, ext, len(data))
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        self._remember(sha, data)
        return ref

    def rewrite_as_delta(self, sha256: str, base: str) -> int:
        """Re-encode a stored object as a delta of `base`. Returns the bytes saved (0 when a delta does not pay or
        the object is already a delta). The original bytes are rebuilt and verified before the old file goes."""
        old = self.find(sha256)
        if old.suffix == ".zsd" or base == sha256 or self.base_chain_contains(base, sha256):
            return 0
        data = self.read(sha256)
        enc = self._encode_delta(data, base)
        if enc is None or len(enc[0]) >= old.stat().st_size:
            return 0
        ext = old.name.split(".")[1]
        new = old.with_name(f"{sha256}.{ext}.zsd")
        fd, tmp = tempfile.mkstemp(dir=old.parent, prefix=".tmp-")
        with os.fdopen(fd, "wb") as f:
            f.write(enc[0])
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, new)
        os.chmod(new, stat.S_IREAD)
        self._cache.pop(sha256, None)
        self.verify(sha256, path=new)
        saved = old.stat().st_size - new.stat().st_size
        os.chmod(old, stat.S_IREAD | stat.S_IWRITE)
        old.unlink()
        return saved

    def base_chain_contains(self, sha256: str, target: str) -> bool:
        cur: str | None = sha256
        while cur is not None:
            if cur == target:
                return True
            cur = self.base_of(cur)
        return False

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

    def _existing(self, path: Path, sha: str, ext: str, size: int) -> RawRef:
        if path.suffix == ".zsd":
            with path.open("rb") as f:
                f.seek(_DELTA_HEAD)
                stored = zstandard.frame_content_size(f.read(18))
        elif path.suffix == ".zst":
            with path.open("rb") as f:
                stored = zstandard.frame_content_size(f.read(18))
        else:
            stored = path.stat().st_size
        if stored != size:
            raise RawStoreError(f"raw object {sha} is stored with {stored} bytes, offered {size}")
        return RawRef(sha, normalize_ext(ext), size, path, created=False)
