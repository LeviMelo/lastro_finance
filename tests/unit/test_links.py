"""A ticker that moves to a new ISIN on the next session links the two instruments; a ticker reused years later
does not."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import polars as pl

from fin.config import Zones
from fin.core import links
from fin.store.tables import write_parquet


def _price(rows: list[tuple[str, str, date, str]]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "instrument_id": [r[0] for r in rows],
            "ticker": [r[1] for r in rows],
            "trade_date": [r[2] for r in rows],
            "market_segment": ["lote_padrao"] * len(rows),
            "close": [Decimal(r[3]) for r in rows],
        }
    )


def test_ticker_continuity(zones: Zones) -> None:
    rows = [
        ("IA", "ABCD3", date(2020, 1, 2), "10"),
        ("IA", "ABCD3", date(2020, 1, 3), "10"),
        ("IB", "ABCD3", date(2020, 1, 6), "10.1"),  # next session, new ISIN: linked
        ("IC", "WXYZ3", date(2020, 1, 2), "5"),
        ("IC", "WXYZ3", date(2020, 1, 3), "5"),
        ("ID", "WXYZ3", date(2023, 5, 2), "7"),  # the same ticker years later: not linked
        ("IX", "OTHR3", date(2020, 1, 6), "1"),
        ("IX", "OTHR3", date(2020, 1, 7), "1"),
        ("IX", "OTHR3", date(2020, 1, 8), "1"),
        ("IX", "OTHR3", date(2020, 1, 9), "1"),
        ("IX", "OTHR3", date(2020, 1, 10), "1"),
        ("IX", "OTHR3", date(2020, 1, 13), "1"),
        ("IX", "OTHR3", date(2023, 5, 2), "1"),
    ]
    write_parquet(_price(rows), zones.core / "price_daily" / "year=2020.parquet")
    out = links.ticker_continuity(zones)
    assert out.select("from_instrument_id", "to_instrument_id").rows() == [("IA", "IB")]
    assert abs(out["price_ratio"][0] - 10 / 10.1) < 1e-12
