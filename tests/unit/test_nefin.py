"""NEFIN factors: exact decimals (some in exponent notation), daily and monthly shapes, the row counter dropped."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import polars as pl
import pytest

from fin.ingest import nefin

FIX = Path(__file__).parents[1] / "fixtures" / "nefin"


def _row(ds: str) -> dict[str, Any]:
    return {"raw_sha256": "a" * 64, "ingest_run_id": "r", "dataset_id": ds}


def _parse(name: str, ds: str) -> pl.DataFrame:
    good, bad = nefin.FACTOR.split(nefin.parse_factors((FIX / name).read_bytes(), _row(ds)))
    assert bad.height == 0
    return good


def test_daily_value_weighted() -> None:
    df = _parse("nefin_factors_head25_tail5.csv", "nefin_factors")
    assert df.height == 30 and df["frequency"].unique().to_list() == ["D"] and df["weighting"][0] == "value"
    first = df.row(0, named=True)
    assert first["period_start"] == date(2001, 1, 2) and first["smb"] == Decimal("-0.0044790252105487")
    assert first["risk_free"] == Decimal("0.0005785165382947")
    assert df["period_start"][-1] == date(2026, 9, 8) and df["rm_minus_rf"][-1] == Decimal("0.010312068088414")


def test_monthly_equally_weighted_dataset_id_sets_the_weighting() -> None:
    df = _parse("nefin_factors_monthly.csv", "nefin_factors_equally_weighted_monthly")
    assert df.height == 308 and set(df["weighting"]) == {"equal"} and set(df["frequency"]) == {"M"}
    assert df["period_start"][0] == date(2001, 1, 1) and df["period_start"][-1] == date(2026, 8, 1)
    assert df["wml"][0] == Decimal("-0.0212409118027145")


def test_exponent_notation_is_exact() -> None:
    blob = b'"","Date","Rm_minus_Rf","SMB","HML","WML","IML","Risk_Free"\n"1",2001-01-02,7.18e-05,0,0,0,0,0.0005\n'
    assert nefin.parse_factors(blob, _row("nefin_factors"))["rm_minus_rf"][0] == Decimal("0.0000718")


def test_unexpected_header_is_a_layout_error() -> None:
    with pytest.raises(nefin.LayoutError):
        nefin.parse_factors(b"Date,X\n2001-01-02,1\n", _row("nefin_factors"))
