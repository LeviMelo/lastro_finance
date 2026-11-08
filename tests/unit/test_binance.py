"""Binance klines: millisecond and microsecond files give the same UTC days; prices exact."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from fin.ingest import binance

FIX = Path(__file__).parents[1] / "fixtures" / "binance"
ROW = {"raw_sha256": "x", "ingest_run_id": "r"}


def test_millisecond_and_microsecond_times() -> None:
    old = binance.parse_zip((FIX / "BTCBRL-1d-2020-10.zip").read_bytes(), ROW)
    new = binance.parse_zip((FIX / "BTCBRL-1d-2026-10.zip").read_bytes(), ROW)
    assert old["day"][0] == date(2020, 10, 13) and new["day"][0] == date(2026, 10, 1)
    assert new["day"].is_sorted() and new["day"].n_unique() == new.height == 31
    r = new.row(0, named=True)
    assert (r["symbol"], r["close"], r["trades"]) == ("BTCBRL", Decimal("443586"), 32272)
    good, bad = binance.KLINE.split(new)
    assert bad.height == 0 and good.height == 31
