"""A held-open, OS-level exclusive lock on a file: alive while its process lives, released when it dies.

Used to tell a live run from a crashed one (two processes may run at once: the daily snapshot job and a backfill).
"""

from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path
from types import TracebackType
from typing import IO, Self


class FileLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._f: IO[bytes] | None = None

    def try_acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        f = self.path.open("a+b")
        try:
            if sys.platform == "win32":
                import msvcrt

                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)  # type: ignore[attr-defined]
        except OSError:
            f.close()
            return False
        self._f = f
        return True

    def release(self, *, remove: bool = True) -> None:
        if self._f is None:
            return
        f, self._f = self._f, None
        try:
            if sys.platform == "win32":
                import msvcrt

                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(f.fileno(), fcntl.LOCK_UN)  # type: ignore[attr-defined]
        finally:
            f.close()
        if remove:
            with contextlib.suppress(OSError):
                os.remove(self.path)

    def __enter__(self) -> Self:
        if not self.try_acquire():
            raise RuntimeError(f"lock {self.path} is held by another process")
        return self

    def __exit__(self, et: type[BaseException] | None, ev: BaseException | None, tb: TracebackType | None) -> None:
        self.release()
