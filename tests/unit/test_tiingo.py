"""Tiingo daily prices: exact decimals, events kept, the token never in the request."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from fin.ingest import tiingo
from fin.ingest.base import Mode

FIX = Path(__file__).parents[1] / "fixtures" / "tiingo"


def test_prices_parse_exactly() -> None:
    row = {"raw_sha256": "x", "ingest_run_id": "r", "dataset_id": "daily",
           "request": json.dumps({"url": f"{tiingo.BASE}/spy/prices"})}  # fmt: skip
    (p,) = list(tiingo.parse_payload((FIX / "SPY_20261102_20261106.json").read_bytes(), row))
    good, bad = tiingo.DAILY.split(p.frame)
    assert bad.height == 0 and good.height == 5
    r = good.row(0, named=True)
    assert (r["ticker"], r["trade_date"], r["close"], r["volume"]) == (
        "SPY",
        date(2026, 11, 2),
        Decimal("752.1"),
        50804340,
    )
    assert r["split_factor"] == Decimal("1") and r["div_cash"] == Decimal("0")


def test_token_travels_in_a_header_not_in_the_request(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("FIN_TIINGO_TOKEN", "secret-value")
    from fin.config import Zones

    spec = next(iter(tiingo.TiingoDaily().discover(Mode.SNAPSHOT, Zones(tmp_path))))
    assert "secret-value" not in json.dumps(spec.request()) and spec.headers["Authorization"] == "Token secret-value"
