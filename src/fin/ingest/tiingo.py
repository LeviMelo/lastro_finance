"""Tiingo end-of-day prices (docs/sources/context_global.md; owner token, OQ-23): US benchmarks behind the B3-listed
ETFs and BDRs, and the ADRs of large Brazilian companies as a USD cross-check of B3 prices. Tier S.

`GET https://api.tiingo.com/tiingo/daily/<TICKER>/prices?startDate=YYYY-MM-DD` with header
`Authorization: Token <token>` (never in the URL, so never in the manifest): a JSON list of
{date "2026-11-02T00:00:00.000Z", open, high, low, close, volume, adjOpen…adjVolume, divCash, splitFactor}
(measured 2026-11-08 on SPY). `GET .../tiingo/daily/<TICKER>` gives name, exchange, start and end dates.
Raw prices and the events (divCash, splitFactor) are kept; Tiingo's adjusted columns are kept as published too
(invariant 6: ours are derived, theirs are a cross-check). Free plan: ~1,000 requests a day, 500 symbols a month.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import date, timedelta
from typing import Any, ClassVar

import polars as pl

from fin.config import Zones, secret
from fin.ingest.base import Connector, Mode, Parsed
from fin.ingest.fetch import FetchSpec
from fin.schema import Column, Contract, Rule

TICKERS = (
    "SPY", "IVV", "QQQ", "VT", "ACWI", "EEM", "EWZ", "TLT", "IEF", "SHY", "GLD", "VNQ",  # benchmarks
    "PBR", "VALE", "ITUB", "BBD", "ABEV",  # ADRs of B3 companies
)  # fmt: skip
BASE = "https://api.tiingo.com/tiingo/daily"
FIRST = date(1990, 1, 1)
RECENT_DAYS = 10
PRICE = pl.Decimal(38, 6)

DAILY = Contract(
    table="staging.tiingo.daily",
    version=1,
    description="A US-listed security's end-of-day prices with Tiingo's dividend and split fields, as published.",
    columns=(
        Column("ticker", pl.String, "Tiingo ticker", "ticker", nullable=False),
        Column("trade_date", pl.Date, "session date", "data", "date", nullable=False),
        Column("open", PRICE, "open", "abertura", "USD"),
        Column("high", PRICE, "high", "máxima", "USD"),
        Column("low", PRICE, "low", "mínima", "USD"),
        Column("close", PRICE, "close", "fechamento", "USD", nullable=False),
        Column("volume", pl.Int64, "shares traded", "volume", "shares"),
        Column("adj_close", PRICE, "Tiingo's adjusted close (cross-check only)", "fechamento ajustado", "USD"),
        Column("div_cash", PRICE, "cash dividend with this ex-date", "dividendo", "USD per share"),
        Column("split_factor", PRICE, "split factor with this ex-date (1 = none)", "fator de desdobramento", "ratio"),
    ),
    rules=(Rule("close_positive", pl.col("close") > 0),),
    key=("ticker", "trade_date"),
)
META = Contract(
    table="staging.tiingo.meta",
    version=1,
    description="Tiingo's description of a ticker: name, exchange, first and last dates.",
    columns=(
        Column("ticker", pl.String, "ticker", "ticker", nullable=False),
        Column("name", pl.String, "name", "nome"),
        Column("exchange", pl.String, "exchangeCode", "bolsa"),
        Column("start_date", pl.Date, "first date with prices", "início", "date"),
        Column("end_date", pl.Date, "last date with prices", "fim", "date"),
    ),
    key=("ticker",),
)
CONTRACTS = {"daily": DAILY, "meta": META}


def _ticker(row: dict[str, Any]) -> str:
    url = str(json.loads(row["request"])["url"])
    return url.removeprefix(BASE + "/").split("/")[0].upper()


def parse_payload(blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
    doc = json.loads(blob, parse_float=str, parse_int=str)
    tk = _ticker(row)
    prov = {"raw_sha256": row["raw_sha256"], "ingest_run_id": row["ingest_run_id"]}
    if row["dataset_id"] == "meta":
        rec = {
            "ticker": tk, "name": doc.get("name"), "exchange": doc.get("exchangeCode"),
            "start_date": date.fromisoformat(doc["startDate"]) if doc.get("startDate") else None,
            "end_date": date.fromisoformat(doc["endDate"]) if doc.get("endDate") else None, "raw_locator": "$",
        }  # fmt: skip
        schema = {c.name: c.dtype for c in META.columns} | {"raw_locator": pl.String}
        yield Parsed(
            "meta", "all", pl.DataFrame([rec], schema=schema).with_columns(**{k: pl.lit(v) for k, v in prov.items()})
        )
        return
    if not isinstance(doc, list):
        raise ValueError(f"Tiingo {tk}: not a list ({str(doc)[:80]})")
    rows = [
        {
            "ticker": tk, "trade_date": r["date"][:10], "open": r.get("open"), "high": r.get("high"),
            "low": r.get("low"), "close": r["close"], "volume": r.get("volume"), "adj_close": r.get("adjClose"),
            "div_cash": r.get("divCash"), "split_factor": r.get("splitFactor"), "raw_locator": f"$[{i}]",
        }
        for i, r in enumerate(doc)
    ]  # fmt: skip
    df = pl.DataFrame(rows, schema={k: pl.String for k in rows[0]} if rows else None, orient="row")
    if not rows:
        return
    df = df.with_columns(
        pl.col("trade_date").str.to_date(),
        *[pl.col(c).cast(PRICE) for c in ("open", "high", "low", "close", "adj_close", "div_cash", "split_factor")],
        pl.col("volume").cast(pl.Float64).cast(pl.Int64),
        **{k: pl.lit(v) for k, v in prov.items()},
    )
    yield Parsed("daily", f"ticker={tk}", df)


class TiingoDaily(Connector):
    """Daily prices of `TICKERS` (whole history on backfill, the last days otherwise) and their metadata."""

    source_id: ClassVar[str] = "tiingo"
    version: ClassVar[str] = "1"
    contracts: ClassVar[dict[str, Any]] = CONTRACTS
    dedup_staging: ClassVar[bool] = True
    min_interval: ClassVar[float] = 1.0

    def discover(self, mode: Mode, zones: Zones, **options: Any) -> Iterable[FetchSpec]:
        from fin.ingest.snapshots import today_brt

        token = secret("tiingo_token")
        if token is None:
            return  # the owner's token is not configured (secrets.toml)
        auth = {"Authorization": f"Token {token}", "Content-Type": "application/json"}
        today = today_brt()
        start = FIRST if mode is Mode.BACKFILL else today - timedelta(days=RECENT_DAYS)
        for tk in options.get("tickers") or TICKERS:
            yield FetchSpec(self.source_id, "daily", f"{BASE}/{tk.lower()}/prices", "json",
                            params={"startDate": start.isoformat()}, headers=auth, reference_date=today,
                            conditional=False, min_bytes=2, locator=f"{tk}|{start.isoformat()}")  # fmt: skip
            if mode is Mode.BACKFILL:
                yield FetchSpec(self.source_id, "meta", f"{BASE}/{tk.lower()}", "json", headers=auth,
                                reference_date=today, conditional=False, min_bytes=2, locator=tk)  # fmt: skip

    def parse(self, blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
        return parse_payload(blob, row)
