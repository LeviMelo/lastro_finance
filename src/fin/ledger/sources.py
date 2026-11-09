"""What the ledger reads from the data layer: asset classes and the corporate events of the tickers held.

- Class: B3's listed-fund registry (`b3_funds_listed`: ETF, ETF-RF, FII, FIAGRO-FII by the 4-letter acronym), then
  core `instrument.asset_class` (share, unit, bdr, fund_quota) through the ticker valid on the trade date.
- Events: core `corporate_event` rows with an applied status (`fin.core.events.APPLIED`; cash events as reported),
  mapped to the ticker the instrument had on the event date (invariant 4: tickers are time-ranged attributes).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import polars as pl

from fin.config import Zones
from fin.core.events import APPLIED
from fin.ledger.engine import CashEvent, StockEvent

FUND_TYPES = {"ETF": "etf", "ETF-CRIPTO": "etf", "ETF-RF": "etf_fixed_income", "FII": "fii", "FIAGRO-FII": "fiagro",
              "ETF-FII": "etf"}  # fmt: skip
INSTRUMENT = {"share": "stock", "unit": "unit", "bdr": "bdr", "fund_quota": "fii"}
STOCK = ("SPLIT", "REVERSE_SPLIT", "BONUS")
CASHK = ("DIVIDEND", "JCP", "INCOME", "AMORTIZATION")


def _read(path: Path) -> pl.DataFrame | None:
    files = list(path.glob("**/*.parquet")) if path.exists() else []
    return pl.read_parquet(files) if files else None


def ticker_map(zones: Zones, tickers: list[str]) -> pl.DataFrame:
    """instrument_id, ticker, vt_from, vt_to for the tickers (empty when the core is absent)."""
    ids = _read(zones.core / "instrument_identifier")
    if ids is None:
        return pl.DataFrame(schema={"instrument_id": pl.String, "ticker": pl.String, "vt_from": pl.Date,
                                    "vt_to": pl.Date})  # fmt: skip
    return ids.filter((pl.col("scheme") == "TICKER") & pl.col("value").is_in(tickers)).select(
        "instrument_id", pl.col("value").alias("ticker"), "vt_from", "vt_to"
    )


def classify(zones: Zones, tickers: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    funds = _read(zones.staging / "b3_funds_listed" / "listed_fund")
    if funds is not None:
        last = funds.sort("snapshot_date").unique(["acronym"], keep="last")
        types = dict(zip(last["acronym"].to_list(), last["type_fund"].to_list(), strict=True))
        for tk in tickers:
            t = types.get(tk[:4])
            if t in FUND_TYPES and tk.endswith("11"):
                out[tk] = FUND_TYPES[t]
    inst = _read(zones.core / "instrument")
    tm = ticker_map(zones, [t for t in tickers if t not in out])
    if inst is not None and tm.height:
        j = tm.join(inst.select("instrument_id", "asset_class"), on="instrument_id").sort("vt_to")
        for tk, ac in j.select("ticker", "asset_class").iter_rows():
            if ac in INSTRUMENT:
                out[tk] = INSTRUMENT[ac]
    for tk in tickers:
        if tk.startswith("Tesouro "):
            out[tk] = "tesouro"
    return out


def events(zones: Zones, tickers: list[str], start: date) -> tuple[list[StockEvent], list[CashEvent]]:
    ev = _read(zones.core / "corporate_event")
    tm = ticker_map(zones, tickers)
    if ev is None or not tm.height:
        return [], []
    links = _read(zones.core / "issuer_instrument")
    ev = ev.filter(pl.col("ex_date") >= start).join(tm, on="instrument_id")
    on = pl.coalesce("data_com", "ex_date")
    ev = ev.filter((on >= pl.col("vt_from")) & (on <= pl.col("vt_to").fill_null(date(9999, 12, 31))))
    payer = {}
    if links is not None and {"instrument_id", "issuer_id"} <= set(links.columns):
        payer = dict(links.select("instrument_id", "issuer_id").unique("instrument_id").iter_rows())
    stock = [
        StockEvent(r["event_id"], r["ticker"], r["event_type"], r["ex_date"], r["ratio_num"], r["ratio_den"])
        for r in ev.filter(
            pl.col("event_type").is_in(STOCK)
            & pl.col("status").is_in(list(APPLIED))
            & pl.col("ratio_num").is_not_null()
        ).iter_rows(named=True)
    ]
    cash = [
        CashEvent(
            r["event_id"],
            r["ticker"],
            r["event_type"],
            r["data_com"] or r["ex_date"],
            r["payment_date"],
            r["approved_on"],
            Decimal(str(r["cash_per_share"])),
            payer.get(r["instrument_id"], ""),
        )
        for r in ev.filter(
            pl.col("event_type").is_in(CASHK)
            & pl.col("cash_per_share").is_not_null()
            & (pl.col("status") != "conflicting")
        ).iter_rows(named=True)
    ]
    return stock, _dedup(cash)


def _dedup(cash: list[CashEvent]) -> list[CashEvent]:
    """One cash event per ticker, kind, data com and amount (sources repeat the same payment)."""
    seen, out = set(), []
    for e in cash:
        k = (e.ticker, e.event_type, e.data_com, e.cash_per_share.quantize(Decimal("0.00000001")))
        if k not in seen:
            seen.add(k)
            out.append(e)
    return out
