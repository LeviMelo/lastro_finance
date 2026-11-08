"""The model panel: one row per line and month with returns and as-of fundamentals, and a column dictionary."""

from __future__ import annotations

from datetime import date

import polars as pl
from test_valuation import test_valuation_point_in_time  # pytest puts tests/unit on the path

from fin.catalog import build as build_catalog
from fin.config import Zones
from fin.export.panel import EQUITY_COLUMNS, build


def test_panel_rows_columns_and_dictionary(zones: Zones) -> None:
    test_valuation_point_in_time(zones)  # ACME3: prices and a filing restated later
    build_catalog(zones)
    out = build(zones, date(2025, 1, 1))
    eq = pl.read_parquet(out / "equity_monthly.parquet")
    assert eq.columns == list(EQUITY_COLUMNS) and eq.height > 0
    assert eq.select(pl.struct("instrument_id", "month").is_unique().all()).item()
    readme = (out / "README.md").read_text(encoding="utf-8")
    assert all(f"`{c}`" in readme for c in EQUITY_COLUMNS)
    assert (out / "macro_monthly.parquet").exists()
