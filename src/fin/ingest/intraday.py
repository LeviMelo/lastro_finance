"""Yahoo 5-minute bars, archived daily (tier U; docs/sources/yahoo_intraday.md).

No free official intraday history exists for B3 (B3's tick tables fail; UP2DATA is paid and for companies). Yahoo
serves 5-minute bars for about the last 60 trading days, so history only exists from the day we start archiving.

- Universe: the most traded standard-lot shares/units (`TOP_SHARES`) and FIIs (`TOP_FIIS`) of COTAHIST's last 90
  days by financial volume, plus Ibovespa (`^BVSP`) and USD/BRL (`BRL=X`).
- Window: from the day after the last archived bar's day (at most `MAX_DAYS` back) to now, so consecutive runs do not
  store overlapping copies.
- Staging `bar`: one row per (symbol, bar start), OHLC rounded to 4 decimals (Yahoo serves single-precision floats:
  45.189998626708984 is 45.19) and volume in units. Bars without a close (no trade) are kept with null prices.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, ClassVar

import polars as pl

from fin.config import Zones
from fin.ingest.base import Connector, Mode, Parsed
from fin.ingest.fetch import FetchSpec
from fin.ingest.http import BROWSER_UA
from fin.ingest.snapshots import held_rows, today_brt
from fin.schema import Column, Contract, Rule

PRICE = pl.Decimal(18, 4)
TOP_SHARES = 120
TOP_FIIS = 60
EXTRA = ("^BVSP", "BRL=X")
MAX_DAYS = 55  # Yahoo serves ~60 days of 5-minute bars (measured 2026-11-07: back to 2026-08-12)

BAR = Contract(
    table="staging.yahoo_intraday.bar",
    version=1,
    description="A 5-minute bar of one symbol as Yahoo served it (tier U).",
    columns=(
        Column("symbol", pl.String, "Yahoo symbol (PETR4.SA, ^BVSP, BRL=X)", "símbolo", nullable=False),
        Column(
            "bar_start",
            pl.Datetime("us", "UTC"),
            "start of the 5-minute bar",
            "início da barra",
            "timestamp",
            nullable=False,
        ),
        Column("currency", pl.String, "meta.currency", "moeda"),
        Column("open", PRICE, "first price", "abertura", "`currency`"),
        Column("high", PRICE, "highest price", "máxima", "`currency`"),
        Column("low", PRICE, "lowest price", "mínima", "`currency`"),
        Column("close", PRICE, "last price", "fechamento", "`currency`"),
        Column("volume", pl.Int64, "quantity traded in the bar", "volume", "units"),
    ),
    rules=(
        Rule("high_ge_low", pl.col("high").is_null() | (pl.col("high") >= pl.col("low"))),
        Rule("volume_non_negative", pl.col("volume").is_null() | (pl.col("volume") >= 0)),
    ),
    key=("symbol", "bar_start"),
)


def _price(x: float | None) -> Decimal | None:
    return None if x is None else Decimal(repr(round(x, 4)))


def parse_bars(blob: bytes, row: dict[str, Any]) -> pl.DataFrame:
    doc = json.loads(blob)["chart"]
    if doc.get("error") or not doc.get("result"):
        raise ValueError(f"Yahoo chart error: {doc.get('error')}")
    res = doc["result"][0]
    meta, ts = res["meta"], res.get("timestamp") or []
    if meta.get("dataGranularity") != "5m":
        raise ValueError(f"Yahoo: granularity {meta.get('dataGranularity')}, expected 5m")
    q = res["indicators"]["quote"][0] if ts else {}
    out = [
        {
            "symbol": meta["symbol"],
            "bar_start": datetime.fromtimestamp(t, UTC),
            "currency": meta.get("currency"),
            "open": _price(q["open"][i]),
            "high": _price(q["high"][i]),
            "low": _price(q["low"][i]),
            "close": _price(q["close"][i]),
            "volume": q["volume"][i],
            "raw_locator": f"$.chart.result[0].timestamp[{i}]",
        }
        for i, t in enumerate(ts)
    ]
    schema = {c.name: c.dtype for c in BAR.columns} | {"raw_locator": pl.String}
    return pl.DataFrame(out, schema=schema, orient="row").with_columns(
        pl.lit(row["raw_sha256"]).alias("raw_sha256"), pl.lit(row["ingest_run_id"]).alias("ingest_run_id")
    )


class YahooIntraday(Connector):
    source_id: ClassVar[str] = "yahoo_intraday"
    version: ClassVar[str] = "1"
    user_agent: ClassVar[str | None] = BROWSER_UA
    contracts: ClassVar[dict[str, Contract]] = {"bar": BAR}
    dedup_staging: ClassVar[bool] = True  # each window re-serves the end of the previous one
    URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

    @staticmethod
    def universe(zones: Zones, days: int = 90) -> list[str]:
        quotes = zones.staging / "b3_cotahist" / "quote"
        if not quotes.exists():
            return list(EXTRA)
        since = today_brt() - timedelta(days=days)
        vol = (
            pl.scan_parquet(quotes / "**" / "*.parquet", hive_partitioning=False)
            .filter((pl.col("trade_date") >= since) & (pl.col("tpmerc") == 10) & pl.col("codbdi").is_in(["02", "12"]))
            .group_by("ticker", "codbdi")
            .agg(pl.col("volume").cast(pl.Float64).sum())
            .collect()
        )
        top = [
            vol.filter(pl.col("codbdi") == c).sort("volume", descending=True)["ticker"].head(n).to_list()
            for c, n in (("02", TOP_SHARES), ("12", TOP_FIIS))
        ]
        return [f"{t}.SA" for t in sorted(top[0] + top[1])] + list(EXTRA)

    def discover(self, mode: Mode, zones: Zones, **options: Any) -> Iterable[FetchSpec]:
        now = datetime.now(UTC)
        held = held_rows(zones, self.source_id, "bars_5m")
        last: dict[str, datetime] = {}
        if held.height:
            for note, at in zip(held["notes"].to_list(), held["fetched_at"].to_list(), strict=True):
                if note and (note not in last or at > last[note]):
                    last[note] = at
        symbols = options.get("tickers") or self.universe(zones)
        for sym in symbols:
            sym = sym if sym.startswith("^") or "=" in sym or sym.endswith(".SA") else f"{sym}.SA"
            start = now - timedelta(days=MAX_DAYS)
            if sym in last:
                start = max(start, last[sym].replace(hour=0, minute=0, second=0, microsecond=0))
            yield FetchSpec(
                self.source_id,
                "bars_5m",
                self.URL.format(symbol=sym),
                "json",
                params={"interval": "5m", "period1": int(start.timestamp()), "period2": int(now.timestamp())},
                reference_date=today_brt(),
                conditional=False,
                absent_status=frozenset({404}),
                locator=sym,
            )

    def parse(self, blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
        df = parse_bars(blob, row)
        sym = df["symbol"][0] if df.height else "empty"
        yield Parsed("bar", f"symbol={sym}", df)
