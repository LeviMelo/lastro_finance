"""B3 fixed-income BDI tables (drp.b3.com.br): layout from real answers, exact decimals, drift refused."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import polars as pl
import pytest

from fin.ingest import b3_fixed_income as fi
from fin.ingest.base import NotData
from fin.schema import Contract

FIX = Path(__file__).parents[1] / "fixtures" / "b3_fixed_income"


def _row(ds: str, locator: str = "page=1") -> dict[str, Any]:
    return {"raw_sha256": "a" * 64, "ingest_run_id": "r", "dataset_id": ds, "notes": locator}


def _one(blob: bytes, ds: str, contract: Contract, locator: str = "page=1") -> pl.DataFrame:
    parts = list(fi.PARSERS[ds](blob, _row(ds, locator)))
    assert len(parts) == 1
    assert parts[0].partition == "ref_date=2024-06-03"
    good, bad = contract.split(parts[0].frame)
    assert bad.height == 0
    return good


def test_trade_page_parses_exactly() -> None:
    df = _one((FIX / "trade_20240603_p1.json").read_bytes(), "Trade", fi.FI_TRADE)
    assert df.height == 1000
    assert set(df["ref_date"]) == {date(2024, 6, 3)}
    assert set(df["situation"]) == {"Confirmado", "Ajustado B3", "Cancelado B3", "Cancelado"}
    deb = df.filter(pl.col("ticker") == "CLTM14")
    assert deb["price_brl"].to_list() == [Decimal("981.250000000000")]
    assert deb["rate_pct"].to_list() == [Decimal("7.870000000000")]
    assert deb["volume_brl"].to_list() == [Decimal("246293.750000000000")]
    assert deb["isin"].to_list() == ["BRCLTMDBS039"]
    assert df["raw_locator"][0] == "page=1|row=0"
    assert df["trade_code"].str.starts_with("#").all()


def test_trade_last_page_and_rate_nulls() -> None:
    df = _one((FIX / "trade_20240603_p16.json").read_bytes(), "Trade", fi.FI_TRADE, "page=16")
    assert df.height == 284
    assert df["rate_pct"].null_count() > 0
    assert df["raw_locator"][0] == "page=16|row=0"


def test_settlement_and_stock() -> None:
    sale = _one((FIX / "saleoff_20240603.json").read_bytes(), "SaleOff", fi.FI_SETTLEMENT)
    assert sale.height == 33
    assert sale["operation_date"].null_count() == 0
    stock = _one((FIX / "stock_20240603.json").read_bytes(), "Stock", fi.FI_STOCK)
    assert stock.height == 11
    assert stock["volume_market_brl"].max() is not None


def test_changed_columns_raise() -> None:
    doc = json.loads((FIX / "stock_20240603.json").read_bytes())
    doc["table"]["columns"][3]["name"] = "QuantityIssuedX"
    with pytest.raises(fi.LayoutError, match="columns changed"):
        list(fi.parse_stock(json.dumps(doc).encode(), _row("Stock")))


def test_dtref_mismatch_raises() -> None:
    doc = json.loads((FIX / "stock_20240603.json").read_bytes())
    doc["table"]["values"][0][1] = "2024-06-04T00:00:00"
    with pytest.raises(fi.LayoutError, match="DtRef"):
        list(fi.parse_stock(json.dumps(doc).encode(), _row("Stock")))


def test_not_json_is_not_data() -> None:
    with pytest.raises(NotData):
        list(fi.parse_trade(b"<html>blocked</html>", _row("Trade")))


def test_empty_day_parses_to_nothing() -> None:
    doc = json.loads((FIX / "stock_20240603.json").read_bytes())
    doc["table"]["values"] = []
    assert list(fi.parse_stock(json.dumps(doc).encode(), _row("Stock"))) == []


def test_paged() -> None:
    c = fi.B3FixedIncome()
    spec = c._spec("Trade", date(2024, 6, 3), 1)  # pyright: ignore[reportPrivateUsage]
    assert spec.url.endswith("/Trade/2024-06-03/2024-06-03/1/1000") and spec.method == "POST"
    follow = list(c.follow(spec, (FIX / "trade_20240603_p1.json").read_bytes()))
    assert [f.locator for f in follow] == [f"page={p}" for p in range(2, 17)]
    assert list(c.follow(follow[0], b"{}")) == []
