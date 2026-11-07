"""The connector interface and the one pipeline every connector runs through (PLAN §4.12).

    discover(mode) -> FetchSpecs -> fetch -> raw + manifest
    parse(raw bytes, manifest row) -> Parsed frames (source-shaped, with provenance)
    contract.split -> staging/<source>/<dataset>/<partition>/<raw_sha256>.parquet + quarantine
    derive(zones) -> core/derived tables built from staging (optional)

Staging holds one file per (dataset, partition, raw object), so parsing the same object again replaces the same file:
idempotent by construction.

**Re-sent files keep only what changed (ADR-0014).** A connector with `dedup_staging` gets, for each new version of a
file, only the rows that are not identical (all data columns) to a row of the previous version of the same file.
A full history re-uploaded daily thus adds the rows of the new day and any restated ones, not a second copy of the
past; A→B→A still records the return to A.

`reparse` runs the same parse/validate/load from the manifest alone, which is what `fin rebuild --from-raw` does.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import asdict, dataclass
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


class NotData(ValueError):
    """The archived object is not the data asked for: an error page served with HTTP 200. Raw keeps it (immutable);
    parsing counts it under `<source>/not_data` and moves on. Fetchers should reject such pages up front
    (`FetchSpec.content_types`)."""


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
    dedup_staging: ClassVar[bool] = False  # its files are re-sent whole: keep only rows that changed (ADR-0014)

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


_NOT_DATA_COLUMNS = ("raw_sha256", "raw_locator", "ingest_run_id", "kt_first_seen_at")


def _data_columns(frame: pl.DataFrame) -> list[str]:
    return [c for c in frame.columns if c not in _NOT_DATA_COLUMNS]


def load(
    connector: Connector,
    zones: Zones,
    run: IngestRun,
    blob: bytes,
    row: dict[str, Any],
    previous: tuple[bytes, dict[str, Any]] | None = None,
) -> None:
    before: dict[tuple[str, str], pl.DataFrame] = {}
    if previous is not None and connector.dedup_staging:
        try:
            for p in connector.parse(*previous):
                key = (p.dataset_id, p.partition)
                before[key] = pl.concat([before[key], p.frame]) if key in before else p.frame
        except Exception:  # an unparseable previous version (error page): nothing to compare with
            before = {}
    for parsed in connector.parse(blob, row):
        contract = connector.contracts[parsed.dataset_id]
        frame = parsed.frame
        old = before.get((parsed.dataset_id, parsed.partition))
        if old is not None and frame.height:
            cols = _data_columns(frame)
            kept = frame.join(old.select(cols).unique(), on=cols, how="anti", nulls_equal=True, maintain_order="left")
            run.count(f"{parsed.dataset_id}:unchanged", in_=frame.height - kept.height)
            frame = kept
        valid, rejected = contract.split(frame)
        sha = row["raw_sha256"]
        base = f"{connector.source_id}/{parsed.dataset_id}/{parsed.partition}/{sha}.parquet"
        write_parquet(valid, zones.staging / base)
        q = zones.quarantine / base
        if rejected.height:
            write_parquet(rejected, q)
        else:
            q.unlink(missing_ok=True)
        run.count(parsed.dataset_id, in_=frame.height, out=valid.height, quarantined=rejected.height)


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
            for mrow, new in out.members:
                if new:
                    member = asdict(mrow)
                    prev = _previous(connector, raw, run.manifest.read(), member) if connector.dedup_staging else None
                    _load_isolated(connector, zones, run, raw.read(mrow.raw_sha256), member, prev)
            if not out.new_object:
                continue  # already archived and parsed when first seen; a rebuild re-parses it from raw
            row = {
                "raw_sha256": out.row.raw_sha256,
                "ingest_run_id": out.row.ingest_run_id,
                "source_reference_date": out.row.source_reference_date,
                "dataset_id": out.row.dataset_id,
                "fetched_at": out.row.fetched_at,
                "request": out.row.request,
                "notes": out.row.notes,
            }
            prev = _previous(connector, raw, run.manifest.read(), row) if connector.dedup_staging else None
            _load_isolated(connector, zones, run, blob, row, prev)
        connector.derive(zones, run)
    finally:
        client.close()
    return errors


def reparse(connector: Connector, zones: Zones, run: IngestRun, manifest: pl.DataFrame) -> None:
    """Re-derive this connector's staging from the manifest and raw alone (one parse per distinct object). Its
    staging and quarantine are cleared first, so nothing of an earlier parser survives."""
    import shutil

    for zone in (zones.staging, zones.quarantine):
        shutil.rmtree(zone / connector.source_id, ignore_errors=True)
    raw = RawStore(zones.raw)
    rows = (
        manifest.filter((pl.col("source_id") == connector.source_id) & (pl.col("http_status") == 200))
        .sort("fetched_at")
        .unique(subset=["dataset_id", "raw_sha256"], keep="first", maintain_order=True)
    )
    last: dict[tuple[str, str | None], dict[str, Any]] = {}
    for row in rows.iter_rows(named=True):
        group = (row["dataset_id"], row["notes"])
        prev_row = last.get(group) if connector.dedup_staging else None
        prev = (raw.read(prev_row["raw_sha256"]), prev_row) if prev_row is not None else None
        _load_isolated(connector, zones, run, raw.read(row["raw_sha256"]), row, prev)
        last[group] = row
    connector.derive(zones, run)


def _previous(
    connector: Connector, raw: RawStore, manifest: pl.DataFrame, row: dict[str, Any]
) -> tuple[bytes, dict[str, Any]] | None:
    """The version stored just before `row` for the same source, dataset and locator."""
    m = manifest.filter(
        (pl.col("source_id") == connector.source_id)
        & (pl.col("dataset_id") == row["dataset_id"])
        & (pl.col("http_status") == 200)
        & (pl.col("raw_sha256") != row["raw_sha256"])
        & (pl.col("fetched_at") < row["fetched_at"])
        & (pl.col("notes").is_null() if row.get("notes") is None else pl.col("notes") == row["notes"])
    )
    if m.is_empty():
        return None
    prev = m.sort("fetched_at").row(-1, named=True)
    return raw.read(prev["raw_sha256"]), prev


def _load_isolated(
    connector: Connector,
    zones: Zones,
    run: IngestRun,
    blob: bytes,
    row: dict[str, Any],
    previous: tuple[bytes, dict[str, Any]] | None = None,
) -> None:
    """An object that cannot be parsed is an error of the run, never the end of it: raw is immutable, so one bad
    object would otherwise block every later run and rebuild."""
    try:
        load(connector, zones, run, blob, row, previous)
    except NotData as e:
        run.count(f"{connector.source_id}/not_data", in_=1, quarantined=1)
        run.log("parse.not_data", raw_sha256=row["raw_sha256"], message=str(e))
    except Exception as e:
        run.error(f"{connector.source_id}/parse", f"{type(e).__name__}: {e}", raw_sha256=row["raw_sha256"])


def _default_ua() -> str:
    from fin.ingest.http import DEFAULT_UA

    return DEFAULT_UA
