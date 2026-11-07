"""Tesouro bonds get stable ids; a value restated in a later daily file becomes version 2 of that date."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import polars as pl

from fin.config import Zones
from fin.core import tesouro
from fin.ingest.tesouro import PRICE_RATE
from fin.store.manifest import ManifestRow
from fin.store.runs import IngestRun
from fin.store.tables import write_parquet

T0 = datetime(2026, 11, 6, 9, tzinfo=UTC)


def _stage(zones: Zones, run: IngestRun, sha: str, at: datetime, pu: str) -> None:
    df = pl.DataFrame(
        {
            "title": ["Tesouro Selic"],
            "maturity": [date(2027, 3, 1)],
            "base_date": [date(2026, 11, 5)],
            "buy_rate": [Decimal("0.02")],
            "sell_rate": [Decimal("0.03")],
            "buy_pu": [Decimal(pu)],
            "sell_pu": [Decimal(pu)],
            "base_pu": [Decimal(pu)],
            "raw_sha256": [sha],
            "raw_locator": ["line=2"],
            "ingest_run_id": [run.run_id],
        }
    ).with_columns(
        pl.col(c).cast(PRICE_RATE.schema()[c]) for c in ("buy_rate", "sell_rate", "buy_pu", "sell_pu", "base_pu")
    )
    write_parquet(df, zones.staging / "tesouro_transparente" / "price_rate" / "all" / f"{sha}.parquet")
    run.manifest.append(
        ManifestRow(
            sha,
            "csv",
            "tesouro_transparente",
            "preco_taxa",
            "{}",
            "k",
            at,
            200,
            None,
            1,
            None,
            None,
            date(2026, 11, 6),
            run.run_id,
            "1",
        )
    )


def test_bond_ids_and_restatement_versions(zones: Zones) -> None:
    with IngestRun(zones, "test") as run:
        _stage(zones, run, "a" * 64, T0, "20240.75")
        _stage(zones, run, "b" * 64, T0 + timedelta(days=1), "20240.80")  # the same date restated
    out = tesouro.build(zones)
    assert out["tesouro_bond"] == 1 and out["tesouro_price_daily"] == 2
    p = pl.read_parquet(zones.core / "tesouro_price_daily" / "tesouro_price_daily.parquet").sort("version")
    assert p["version"].to_list() == [1, 2] and p["base_pu"][1] == Decimal("20240.80")
    bond = pl.read_parquet(zones.core / "tesouro_bond" / "tesouro_bond.parquet").row(0, named=True)
    assert bond["instrument_id"] == tesouro.bond_id("Tesouro Selic", "2027-03-01") and bond["indexer"] == "SELIC"
