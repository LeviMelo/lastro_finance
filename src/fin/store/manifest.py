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
        # lookups made at every fetch are dict hits, not scans: a backfill of 225,000 documents re-filtered (and
        # re-built) the whole manifest per document, O(n^2) (2026-11-08)
        self._by_locator: dict[tuple[str, str, str | None], list[dict[str, Any]]] | None = None
        self._by_request: dict[str, dict[str, Any]] = {}

    def append(self, row: ManifestRow) -> None:
        self.journal.append(row.ingest_run_id, asdict(row))
        if self._snapshot is not None:
            self._appended.append(asdict(row))
            self._view = None
        if self._by_locator is not None:
            self._index(asdict(row))

    def _index(self, r: dict[str, Any]) -> None:
        assert self._by_locator is not None
        if r["http_status"] == 200:
            self._by_locator.setdefault((r["source_id"], r["dataset_id"], r["notes"]), []).append(r)
        if r["http_status"] in (200, 304):
            cur = self._by_request.get(r["request_key"])
            if cur is None or r["fetched_at"] >= cur["fetched_at"]:
                self._by_request[r["request_key"]] = r

    def _indexed(self) -> dict[tuple[str, str, str | None], list[dict[str, Any]]]:
        if self._by_locator is None:
            self._by_locator = {}
            for r in self.cached().sort("fetched_at").iter_rows(named=True):
                self._index(r)
        return self._by_locator

    def versions(self, source_id: str, dataset_id: str, notes: str | None) -> list[dict[str, Any]]:
        """Every stored (200) row of the same source, dataset and locator, oldest first."""
        return sorted(self._indexed().get((source_id, dataset_id, notes), []), key=lambda r: r["fetched_at"])

    def previous_version(self, source_id: str, dataset_id: str, notes: str | None) -> str | None:
        """The newest object stored for the same source, dataset and locator: the base of a delta (ADR-0014)."""
        rows = self.versions(source_id, dataset_id, notes)
        return str(rows[-1]["raw_sha256"]) if rows else None

    def latest_for_request(self, request_key: str) -> dict[str, Any] | None:
        """The newest row of a request that stored or confirmed an object; used for conditional requests."""
        self._indexed()
        return self._by_request.get(request_key)

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
