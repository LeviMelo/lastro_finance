"""The catalog holds views only: it builds over whatever Parquet exists, skips views whose files do not, and a
partition folder never shadows a column of the same name."""

from __future__ import annotations

import duckdb
import polars as pl

from fin.catalog import build
from fin.config import Zones
from fin.store.tables import write_parquet


def test_views_over_existing_files_only(zones: Zones) -> None:
    write_parquet(
        pl.DataFrame({"instrument_id": ["I1"], "asset_class": ["share"]}),
        zones.core / "instrument" / "instrument.parquet",
    )
    made = build(zones)
    assert made == ["instrument"]
    con = duckdb.connect(str(zones.catalog), read_only=True)
    assert con.sql("select asset_class from instrument").fetchall() == [("share",)]


def test_partition_folders_do_not_shadow_columns(zones: Zones) -> None:
    lines = zones.staging / "cvm_dfp_itr" / "statement_line" / "form=dfp" / "year=2024" / "statement=BPA_con"
    docs = zones.staging / "cvm_dfp_itr" / "document" / "form=dfp" / "year=2024"
    row = {
        "form": "dfp", "cnpj": "60.872.504/0001-23", "reference_date": "2024-12-31", "version": 1,
        "company_name": "ITAU", "cd_cvm": "019348", "statement": "BPA", "consolidation": "con",
        "statement_group": "x", "currency": "REAL", "scale": "MIL", "period_order": "ÚLTIMO", "period_start": None,
        "period_end": "2024-12-31", "equity_column": None, "account_code": "1", "account_name": "Ativo Total",
        "value": "2854475000.0", "fixed_account": True, "raw_sha256": "a", "raw_locator": "x", "ingest_run_id": "r",
    }  # fmt: skip
    df = pl.DataFrame([row]).with_columns(pl.col("value").cast(pl.Decimal(38, 10)))
    write_parquet(df, lines / "a.parquet")
    write_parquet(
        pl.DataFrame(
            {
                "form": ["dfp"],
                "cnpj": [row["cnpj"]],
                "reference_date": ["2024-12-31"],
                "version": [1],
                "received_on": ["2025-02-05"],
            }
        ),
        docs / "a.parquet",
    )
    assert "fundamental_fact" in build(zones)
    con = duckdb.connect(str(zones.catalog), read_only=True)
    st, value = con.execute("select statement, value_brl from fundamental_fact").fetchall()[0]
    assert st == "BPA" and str(value).startswith("2854475000000")
