"""CFTC reports stage long: one row per market, date, trader group and side; both date-column names read as ISO."""

from __future__ import annotations

import io
import zipfile
from datetime import date
from pathlib import Path

import polars as pl

from fin.ingest import cftc

FIX = Path(__file__).parents[1] / "fixtures" / "cftc_cot"


def _parse(name: str, dataset: str) -> pl.DataFrame:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("member.txt", (FIX / name).read_bytes())
    df = cftc.parse_report(buf.getvalue(), {"raw_sha256": "a" * 64, "ingest_run_id": "r", "dataset_id": dataset})
    good, bad = cftc.POSITION.split(df)
    assert bad.height == 0
    return good


def test_financial_report_groups() -> None:
    df = _parse("fin_2026_brl.txt", "fut_fin_txt")
    assert set(df["trader_group"]) == {"all", "dealer", "asset_manager", "leveraged_funds", "other_reportable",
                                       "nonreportable"}  # fmt: skip
    assert df["market_name"][0].startswith("BRAZILIAN REAL") and df["report"][0] == "financial"
    per_row = df.group_by("market_code", "report_date").len()["len"].unique().to_list()
    assert per_row == [len(cftc.FIN)]


def test_old_date_column_and_legacy_report() -> None:
    corn = _parse("disagg_2010_corn.txt", "fut_disagg_txt")
    assert corn["report_date"].min() >= date(2010, 1, 1) and set(corn["side"]) >= {"long", "short", "spread"}
    cad = _parse("legacy_2026_cad.txt", "deacot")
    assert "noncommercial" in set(cad["trader_group"]) and cad["report_date"].dt.year().unique().to_list() == [2026]
