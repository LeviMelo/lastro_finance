"""The connector interface and the one pipeline every connector runs through (PLAN §4.12).

    discover(mode) -> FetchSpecs -> fetch -> raw + manifest
    parse(raw bytes, manifest row) -> Parsed frames (source-shaped, with provenance)
    contract.split -> staging/<source>/<dataset>/<partition>/<raw_sha256>.parquet + quarantine
    derive(zones) -> core/derived tables built from staging (optional)

Staging holds one file per (dataset, partition, raw object), so parsing the same object again replaces the same file:
idempotent by construction. `reparse` runs the same parse/validate/load from the manifest alone, which is what
`fin rebuild --from-raw` does.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, ClassVar

import polars as pl

from fin.config import Zones
from fin.ingest.fetch import Fetcher, FetchSpec
from fin.ingest.http import FetchError, PoliteClient
from fin.schema import Contract
from fin.store.raw import RawStore
from fin.store.runs import IngestRun
from fin.store.tables import write_parquet


class Mode(StrEnum):
    BACKFILL = "backfill"
    INCREMENTAL = "incremental"
    SNAPSHOT = "snapshot"  # ephemeral sources: archive what is served today (PLAN §4.1 invariant 13)


@dataclass(frozen=True)
class Parsed:
    dataset_id: str
    partition: str  # e.g. "year=2024", "all"
    frame: pl.DataFrame


class Connector(ABC):
    source_id: ClassVar[str]
    version: ClassVar[str]
    contracts: ClassVar[dict[str, Contract]] = {}
    user_agent: ClassVar[str | None] = None  # None: the default generic UA
    min_interval: ClassVar[float] = 1.0

    @abstractmethod
    def discover(self, mode: Mode, zones: Zones, **options: Any) -> Iterable[FetchSpec]:
        """What to fetch now for this mode."""

    def follow(self, spec: FetchSpec, blob: bytes) -> Iterable[FetchSpec]:
        """Further requests a response implies (pagination). Called after every successful fetch."""
        return ()

    def parse(self, blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
        """Raw bytes to source-shaped frames. Connectors that only archive (snapshot-first) parse nothing yet."""
        return ()

    def derive(self, zones: Zones, run: IngestRun) -> None:
        """Build this source's core/derived tables from its staging tables."""


def load(connector: Connector, zones: Zones, run: IngestRun, blob: bytes, row: dict[str, Any]) -> None:
    for parsed in connector.parse(blob, row):
        contract = connector.contracts[parsed.dataset_id]
        valid, rejected = contract.split(parsed.frame)
        sha = row["raw_sha256"]
        base = f"{connector.source_id}/{parsed.dataset_id}/{parsed.partition}/{sha}.parquet"
        write_parquet(valid, zones.staging / base)
        q = zones.quarantine / base
        if rejected.height:
            write_parquet(rejected, q)
        else:
            q.unlink(missing_ok=True)
        run.count(parsed.dataset_id, in_=parsed.frame.height, out=valid.height, quarantined=rejected.height)


def run_connector(connector: Connector, zones: Zones, run: IngestRun, mode: Mode, **options: Any) -> int:
    """Discover, fetch, parse, validate, load. Returns the number of fetch errors (each also recorded on the run)."""
    raw = RawStore(zones.raw)
    client = PoliteClient(user_agent=connector.user_agent or _default_ua(), min_interval=connector.min_interval)
    fetcher = Fetcher(run, raw, client, connector.version)
    errors = 0
    try:
        queue = list(connector.discover(mode, zones, **options))
        while queue:
            spec = queue.pop(0)
            try:
                out = fetcher.fetch(spec)
            except FetchError as e:
                errors += 1
                run.error(f"{spec.source_id}/{spec.dataset_id}", str(e), url=spec.url, status=e.status)
                continue
            if out is None:
                continue
            blob = raw.read(out.row.raw_sha256)
            queue[:0] = list(connector.follow(spec, blob))
            run.count(f"fetch:{spec.dataset_id}", in_=1, out=int(out.new_object))
            if not out.new_object:
                continue  # already archived and parsed when first seen; a rebuild re-parses it from raw
            row = {
                "raw_sha256": out.row.raw_sha256,
                "ingest_run_id": out.row.ingest_run_id,
                "source_reference_date": out.row.source_reference_date,
                "dataset_id": out.row.dataset_id,
                "fetched_at": out.row.fetched_at,
                "request": out.row.request,
            }
            load(connector, zones, run, blob, row)
        connector.derive(zones, run)
    finally:
        client.close()
    return errors


def reparse(connector: Connector, zones: Zones, run: IngestRun, manifest: pl.DataFrame) -> None:
    """Re-derive this connector's staging from the manifest and raw alone (one parse per distinct object)."""
    raw = RawStore(zones.raw)
    rows = (
        manifest.filter((pl.col("source_id") == connector.source_id) & (pl.col("http_status") == 200))
        .sort("fetched_at")
        .unique(subset=["dataset_id", "raw_sha256"], keep="first", maintain_order=True)
    )
    for row in rows.iter_rows(named=True):
        load(connector, zones, run, raw.read(row["raw_sha256"]), row)
    connector.derive(zones, run)


def _default_ua() -> str:
    from fin.ingest.http import DEFAULT_UA

    return DEFAULT_UA
