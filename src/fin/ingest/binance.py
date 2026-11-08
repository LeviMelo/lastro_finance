"""Binance public bulk data: daily spot klines (docs/sources/binance.md). Crypto is scope priority 3 (ADR-0011:
archived where cheap); the BRL pairs price the crypto ETFs' underlying and USDT/BRL is a market dollar rate.

`https://data.binance.vision/data/spot/monthly/klines/<SYMBOL>/1d/<SYMBOL>-1d-<YYYY-MM>.zip` (one CSV, no header,
1-2 KB) and `.../daily/klines/<SYMBOL>/1d/<SYMBOL>-1d-<YYYY-MM-DD>.zip` for the days of the month not yet in a
monthly file; the S3 listing `https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?delimiter=/&prefix=...`
names the monthly files (measured 2026-11-08; BTCBRL from 2020-10, BTCUSDT from 2017-08).
Columns: open time, open, high, low, close, base volume, close time, quote volume, trades, taker-buy base,
taker-buy quote, ignore. Times are epoch milliseconds until 2024 and **microseconds** in 2026 files (16 digits):
the unit is read from the number of digits. Rows of a daily file reappear in the month's file: staging dedups by
content, the catalog keeps one row per symbol and day.
"""

from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from typing import Any, ClassVar

import polars as pl

from fin.config import Zones
from fin.ingest.base import Connector, Mode, Parsed
from fin.ingest.fetch import FetchSpec
from fin.schema import Column, Contract, Rule

SYMBOLS = ("BTCBRL", "ETHBRL", "USDTBRL", "SOLBRL", "BTCUSDT", "ETHUSDT")
BASE = "https://data.binance.vision/data/spot"
LIST = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
PRICE = pl.Decimal(38, 8)
KEY = re.compile(r"<Key>(data/spot/monthly/klines/[A-Z]+/1d/[A-Z]+-1d-\d{4}-\d{2}\.zip)</Key>")

KLINE = Contract(
    table="staging.binance.kline",
    version=1,
    description="A daily spot kline of a Binance pair (UTC day), as Binance's bulk files publish it.",
    columns=(
        Column("symbol", pl.String, "pair, e.g. BTCBRL", "par", nullable=False),
        Column("day", pl.Date, "UTC day of the open time", "dia (UTC)", "date", nullable=False),
        Column("open", PRICE, "open", "abertura", "quote currency per base unit", nullable=False),
        Column("high", PRICE, "high", "máxima", "quote currency per base unit", nullable=False),
        Column("low", PRICE, "low", "mínima", "quote currency per base unit", nullable=False),
        Column("close", PRICE, "close", "fechamento", "quote currency per base unit", nullable=False),
        Column("base_volume", PRICE, "volume in the base asset", "volume (ativo base)", "base units"),
        Column("quote_volume", PRICE, "volume in the quote asset", "volume (moeda de cotação)", "quote currency"),
        Column("trades", pl.Int64, "number of trades", "negócios", "count"),
        Column("taker_buy_base", PRICE, "taker buy volume, base", "compra agressora (base)", "base units"),
        Column("taker_buy_quote", PRICE, "taker buy volume, quote", "compra agressora (cotação)", "quote currency"),
    ),
    rules=(Rule("low_le_high", pl.col("low") <= pl.col("high")),),
    key=("symbol", "day"),
)
CONTRACTS = {"kline": KLINE}


class LayoutError(ValueError):
    pass


def _day(stamp: str) -> date:
    n = int(stamp)
    seconds = n / 1_000_000 if len(stamp) >= 16 else n / 1_000  # microseconds (2025-) or milliseconds
    return datetime.fromtimestamp(seconds, tz=UTC).date()


def parse_zip(blob: bytes, row: dict[str, Any]) -> pl.DataFrame:
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        names = z.namelist()
        if len(names) != 1 or not names[0].endswith(".csv"):
            raise LayoutError(f"Binance: members {names}")
        text = z.read(names[0]).decode("ascii")
        symbol = names[0].split("-", 1)[0]
    out: list[dict[str, Any]] = []
    for i, line in enumerate(text.splitlines(), start=1):
        f = line.split(",")
        if len(f) != 12:
            raise LayoutError(f"Binance {names[0]} line {i}: {len(f)} fields")
        out.append({
            "symbol": symbol, "day": _day(f[0]), "open": f[1], "high": f[2], "low": f[3], "close": f[4],
            "base_volume": f[5], "quote_volume": f[7], "trades": int(f[8]), "taker_buy_base": f[9],
            "taker_buy_quote": f[10], "raw_locator": f"member={names[0]};line={i}",
        })  # fmt: skip
    df = pl.DataFrame(out, orient="row")
    return df.with_columns(
        *[pl.col(c).cast(PRICE) for c in ("open", "high", "low", "close", "base_volume", "quote_volume",
                                          "taker_buy_base", "taker_buy_quote")],
        pl.lit(row["raw_sha256"]).alias("raw_sha256"), pl.lit(row["ingest_run_id"]).alias("ingest_run_id"),
    )  # fmt: skip


class BinanceKlines(Connector):
    """Daily klines of a few BRL and USDT pairs: monthly files from the S3 listing, plus this month's daily files."""

    source_id: ClassVar[str] = "binance"
    version: ClassVar[str] = "1"
    contracts: ClassVar[dict[str, Any]] = CONTRACTS
    dedup_staging: ClassVar[bool] = True
    min_interval: ClassVar[float] = 0.2

    def __init__(self) -> None:
        self._held: set[str] = set()

    def discover(self, mode: Mode, zones: Zones, **options: Any) -> Iterable[FetchSpec]:
        from fin.ingest.snapshots import held_rows, today_brt

        held = held_rows(zones, self.source_id, "monthly")
        self._held = set(held["notes"].drop_nulls().to_list()) if held.height else set()  # a month file never changes
        for s in options.get("symbols") or SYMBOLS:
            yield FetchSpec(
                self.source_id, "listing", LIST, "xml",
                params={"delimiter": "/", "prefix": f"data/spot/monthly/klines/{s}/1d/"},
                reference_date=today_brt(), conditional=False, locator=s,
            )  # fmt: skip
            today = datetime.now(tz=UTC).date()
            d = today.replace(day=1)
            if today.day <= 3:  # the previous month's file may not be published yet
                d = (d - timedelta(days=1)).replace(day=1)
            while d < today:
                yield FetchSpec(
                    self.source_id, "daily", f"{BASE}/daily/klines/{s}/1d/{s}-1d-{d.isoformat()}.zip", "zip",
                    reference_date=d, absent_status=frozenset({404}), locator=f"{s};{d.isoformat()}",
                )  # fmt: skip
                d += timedelta(days=1)

    def follow(self, spec: FetchSpec, blob: bytes) -> Iterable[FetchSpec]:
        if spec.dataset_id != "listing":
            return []
        out = []
        for key in KEY.findall(blob.decode("utf-8")):
            if key.rsplit("/", 1)[1] in self._held:
                continue
            month = key.rsplit("-1d-", 1)[1].removesuffix(".zip")
            out.append(
                FetchSpec(
                    self.source_id,
                    "monthly",
                    f"https://data.binance.vision/{key}",
                    "zip",
                    reference_date=date.fromisoformat(month + "-01"),
                    locator=key.rsplit("/", 1)[1],
                    conditional=False,
                )
            )
        return out

    def parse(self, blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
        if row["dataset_id"] == "listing":
            return
        yield Parsed("kline", "all", parse_zip(blob, row))
