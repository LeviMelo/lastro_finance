"""`ingest_run`: one row per pipeline run, with its counts and errors (PLAN §4.12 observability).

An `IngestRun` is a context manager. It owns a run id (sortable: `YYYYMMDDTHHMMSSZ-<6 hex>`), a JSON-lines log
under `logs/`, the counts in/out/quarantined per dataset, and seals the manifest and the run record on exit.
A run that dies without exiting is found by `recover()` and sealed with status `crashed`.
"""

from __future__ import annotations

import json
import secrets
import subprocess
import traceback
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Self

import pyarrow as pa

from fin import __version__
from fin.config import REPO_ROOT, Zones
from fin.store.journal import Journal
from fin.store.lock import FileLock
from fin.store.manifest import Manifest

SCHEMA = pa.schema(
    [
        ("ingest_run_id", pa.string()),
        ("command", pa.string()),
        ("event", pa.string()),  # start | end
        ("at", pa.timestamp("us", tz="UTC")),
        ("status", pa.string()),  # running | ok | failed | crashed
        ("code_version", pa.string()),
        ("counts", pa.string()),  # JSON {dataset: {in, out, quarantined}}
        ("errors", pa.string()),  # JSON list
    ]
)


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_run_id(now: datetime | None = None) -> str:
    t = (now or utc_now()).strftime("%Y%m%dT%H%M%SZ")
    return f"{t}-{secrets.token_hex(3)}"


def code_version() -> str:
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, timeout=5
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return __version__
    if not sha:
        return __version__
    return f"{__version__}+{sha}{'.dirty' if dirty else ''}"


class IngestRun:
    def __init__(self, zones: Zones, command: str) -> None:
        self.zones = zones
        self.command = command
        self.run_id = new_run_id()
        self.manifest = Manifest(zones.manifest)
        self.table = Journal(zones.runs, SCHEMA)
        self.counts: dict[str, dict[str, int]] = defaultdict(lambda: {"in": 0, "out": 0, "quarantined": 0})
        self.errors: list[dict[str, Any]] = []
        self._log_path = zones.logs / f"{self.run_id}.jsonl"
        self._lock = FileLock(_lock_path(zones, self.run_id))

    def __enter__(self) -> Self:
        if not self._lock.try_acquire():
            raise RuntimeError(f"run {self.run_id} is already locked")
        recover(self.zones)
        self.zones.logs.mkdir(parents=True, exist_ok=True)
        self.table.append(self.run_id, self._row("start", "running"))
        self.log("run.start", command=self.command)
        return self

    def __exit__(self, et: type[BaseException] | None, ev: BaseException | None, tb: TracebackType | None) -> None:
        if ev is not None:
            self.error("run", f"{type(ev).__name__}: {ev}", trace="".join(traceback.format_exception(et, ev, tb)))
        status = "failed" if (ev is not None or self.errors) else "ok"
        self.log("run.end", status=status, counts=dict(self.counts))
        self.table.append(self.run_id, self._row("end", status))
        self.manifest.seal(self.run_id)
        self.table.seal(self.run_id)
        self._lock.release()

    def count(self, dataset: str, *, in_: int = 0, out: int = 0, quarantined: int = 0) -> None:
        c = self.counts[dataset]
        c["in"] += in_
        c["out"] += out
        c["quarantined"] += quarantined

    def error(self, where: str, message: str, **extra: Any) -> None:
        self.errors.append({"where": where, "message": message, **extra})
        self.log("error", where=where, message=message)

    def log(self, event: str, **fields: Any) -> None:
        rec = {"at": utc_now().isoformat(), "run": self.run_id, "event": event, **fields}
        with self._log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")

    def _row(self, event: str, status: str) -> dict[str, Any]:
        return {
            "ingest_run_id": self.run_id,
            "command": self.command,
            "event": event,
            "at": utc_now(),
            "status": status,
            "code_version": code_version(),
            "counts": json.dumps(dict(self.counts), sort_keys=True),
            "errors": json.dumps(self.errors, ensure_ascii=False, default=str),
        }


def recover(zones: Zones) -> list[str]:
    """Seal what crashed runs left: their manifest journals, and their run journals with an `end/crashed` row.

    A run whose lock is still held belongs to a live process and is left alone.
    """
    table = Journal(zones.runs, SCHEMA)
    manifest = Manifest(zones.manifest)
    journals = zones.runs / "_journal"
    crashed: list[str] = []
    if journals.exists():
        for p in sorted(journals.glob("*.jsonl")):
            run_id = p.stem
            probe = FileLock(_lock_path(zones, run_id))
            if not probe.try_acquire():
                continue
            probe.release()
            manifest.journal.seal(run_id)
            text = p.read_text(encoding="utf-8")
            if '"event": "end"' not in text:
                table.append(
                    run_id,
                    {
                        "ingest_run_id": run_id,
                        "command": None,
                        "event": "end",
                        "at": utc_now(),
                        "status": "crashed",
                        "code_version": None,
                        "counts": None,
                        "errors": None,
                    },
                )
                crashed.append(run_id)
            table.seal(run_id)
    return crashed


def _lock_path(zones: Zones, run_id: str) -> Path:
    return zones.runs / "_locks" / f"{run_id}.lock"
