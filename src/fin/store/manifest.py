"""The L1 manifest: one row per fetch that produced or re-confirmed a raw object (PLAN §4.2).

A 2xx fetch records the object it stored. A 304 (not modified) records the object the previous fetch stored, so the
manifest also says when a payload was last confirmed unchanged. `kt_first_seen_at` of any fact is the earliest
`fetched_at` of its raw object here.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import polars as pl
import pyarrow as pa

from fin.store.journal import Journal

SCHEMA = pa.schema(
    [
        ("raw_sha256", pa.string()),
        ("raw_ext", pa.string()),
        ("source_id", pa.string()),
        ("dataset_id", pa.string()),
        ("request", pa.string()),  # canonical JSON, credentials redacted
        ("request_key", pa.string()),  # sha256 of `request`: the identity of "the same request"
        ("fetched_at", pa.timestamp("us", tz="UTC")),
        ("http_status", pa.int32()),
        ("content_type", pa.string()),
        ("bytes", pa.int64()),
        ("etag", pa.string()),
        ("last_modified", pa.string()),
        ("source_reference_date", pa.date32()),
        ("ingest_run_id", pa.string()),
        ("connector_version", pa.string()),
        ("notes", pa.string()),
    ]
)

_SECRET_KEYS = ("token", "password", "passwd", "secret", "apikey", "api_key", "authorization", "cookie")


def redact(obj: Any) -> Any:
    if isinstance(obj, Mapping):
        return {
            k: ("<redacted>" if any(s in str(k).lower() for s in _SECRET_KEYS) else redact(v))
            for k, v in obj.items()  # type: ignore[union-attr]
        }
    if isinstance(obj, list | tuple):
        return [redact(v) for v in obj]  # type: ignore[union-attr]
    return obj


def canonical_request(request: Mapping[str, Any]) -> str:
    return json.dumps(redact(request), sort_keys=True, ensure_ascii=False, separators=(",", ":"))


@dataclass(frozen=True)
class ManifestRow:
    raw_sha256: str
    raw_ext: str
    source_id: str
    dataset_id: str
    request: str
    request_key: str
    fetched_at: datetime
    http_status: int
    content_type: str | None
    bytes: int
    etag: str | None
    last_modified: str | None
    source_reference_date: date | None
    ingest_run_id: str
    connector_version: str
    notes: str | None = None


class Manifest:
    def __init__(self, directory: Path) -> None:
        self.journal = Journal(directory, SCHEMA)
        self._snapshot: pl.DataFrame | None = None  # what was on disk at the first lookup of this run
        self._appended: list[dict[str, Any]] = []  # rows this object appended since
        self._view: pl.DataFrame | None = None

    def append(self, row: ManifestRow) -> None:
        self.journal.append(row.ingest_run_id, asdict(row))
        if self._snapshot is not None:
            self._appended.append(asdict(row))
            self._view = None

    def cached(self) -> pl.DataFrame:
        """The manifest as of this run's first lookup plus the rows this run appended: lookups made at every fetch
        (conditional requests, delta bases, staging dedup) must not re-read every journal each time. Rows other
        processes append meanwhile are not seen; they belong to other sources."""
        if self._snapshot is None:
            self._snapshot = self.read()
        if self._view is None:
            extra = pl.DataFrame(self._appended, schema=self._snapshot.schema, orient="row") if self._appended else None
            self._view = self._snapshot if extra is None else pl.concat([self._snapshot, extra])
        return self._view

    def seal(self, run_id: str) -> None:
        self.journal.seal(run_id)

    def recover(self) -> list[str]:
        return self.journal.recover()

    def read(self) -> pl.DataFrame:
        return self.journal.read()

    def previous_version(self, source_id: str, dataset_id: str, notes: str | None) -> str | None:
        """The newest object stored for the same source, dataset and locator: the base of a delta (ADR-0014)."""
        df = self.cached().filter(
            (pl.col("source_id") == source_id)
            & (pl.col("dataset_id") == dataset_id)
            & (pl.col("http_status") == 200)
            & (pl.col("notes").is_null() if notes is None else pl.col("notes") == notes)
        )
        if df.is_empty():
            return None
        return str(df.sort("fetched_at")["raw_sha256"][-1])

    def latest_for_request(self, request_key: str) -> dict[str, Any] | None:
        """The newest row of a request that stored or confirmed an object; used for conditional requests."""
        df = self.cached().filter((pl.col("request_key") == request_key) & pl.col("http_status").is_in([200, 304]))
        if df.is_empty():
            return None
        return df.sort("fetched_at").row(-1, named=True)
