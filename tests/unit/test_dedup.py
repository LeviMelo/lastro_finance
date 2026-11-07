"""A re-sent file adds only the rows that changed since its previous version; a value that returns is recorded."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any, ClassVar

import polars as pl

from fin.config import Zones
from fin.ingest.base import Connector, Mode, Parsed, load
from fin.ingest.fetch import FetchSpec
from fin.schema import Column, Contract
from fin.store.runs import IngestRun

TOY = Contract(
    table="staging.toy.value",
    version=1,
    description="toy",
    columns=(Column("day", pl.String, "day", nullable=False), Column("v", pl.String, "value", nullable=False)),
)


class Toy(Connector):
    source_id: ClassVar[str] = "toy"
    version: ClassVar[str] = "1"
    contracts: ClassVar[dict[str, Contract]] = {"value": TOY}
    dedup_staging: ClassVar[bool] = True

    def discover(self, mode: Mode, zones: Zones, **options: Any) -> Iterable[FetchSpec]:
        return ()

    def parse(self, blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
        rows = json.loads(blob)
        df = pl.DataFrame(rows, schema={"day": pl.String, "v": pl.String}, orient="row").with_columns(
            pl.lit(row["raw_sha256"]).alias("raw_sha256"),
            pl.lit("$").alias("raw_locator"),
            pl.lit(row["ingest_run_id"]).alias("ingest_run_id"),
        )
        yield Parsed("value", "all", df)


def _row(sha: str) -> dict[str, Any]:
    return {"raw_sha256": sha * 64, "ingest_run_id": "r"}


def _staged(zones: Zones, sha: str) -> list[tuple[str, str]]:
    df = pl.read_parquet(zones.staging / "toy" / "value" / "all" / f"{sha * 64}.parquet")
    return list(df.select("day", "v").iter_rows())


def test_only_changed_rows_are_staged(zones: Zones) -> None:
    versions = [
        [["d1", "A"], ["d2", "x"]],
        [["d1", "B"], ["d2", "x"], ["d3", "y"]],  # d1 restated, d3 new
        [["d1", "A"], ["d2", "x"], ["d3", "y"]],  # d1 back to A
    ]
    blobs = [json.dumps(v).encode() for v in versions]
    with IngestRun(zones, "test") as run:
        load(Toy(), zones, run, blobs[0], _row("a"))
        load(Toy(), zones, run, blobs[1], _row("b"), (blobs[0], _row("a")))
        load(Toy(), zones, run, blobs[2], _row("c"), (blobs[1], _row("b")))
        unchanged = run.counts["value:unchanged"]["in"]
    assert _staged(zones, "a") == [("d1", "A"), ("d2", "x")]
    assert _staged(zones, "b") == [("d1", "B"), ("d3", "y")]
    assert _staged(zones, "c") == [("d1", "A")]
    assert unchanged == 1 + 2
