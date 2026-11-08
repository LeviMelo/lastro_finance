"""B3 fixed-income OTC tables of the Boletim Diário with history from `drp.b3.com.br`.


See docs/sources/b3_fixed_income.md.
`POST https://drp.b3.com.br/bdi/table/<Table>/<d>/<d>/<page>/<take>`, body `{}`: the same backend as the BDI of
`arquivos.b3.com.br` (b3_bdi), with a longer window for these tables (measured 2026-11-08):

- `Trade`: one trade of a registered instrument (DEB, CRA, CRI, CFF, LIG, LF, COE...): quantity, PU, volume, rate,
  venue, time, trade id, ISIN, settlement, status. First day served: 2023-03-13.
- `SaleOff`: settlement volume of an instrument type by operation type and method. First day served: 2023-03-01.
- `Stock`: quantity and volume in market and deposited per instrument type. First day served: 2023-03-01.

Every answer is `{"table": {"columns": [...], "values": [[...]], "pageCount": N, ...}, "status", "lastUpdateDate"}`.
`take` is at most 1000 (1500/2000/5000 answer 400). The column names are checked against the layout measured on
2024-06-03 and identical on 2023-06-01 .. 2026-11-06: any other layout raises (`LayoutError`), never parses.
Numbers become exact `Decimal`s (the JSON text, never a float). A trade of a cancelled or adjusted status is kept with
its `situation`: a restatement is a fact (invariant 3). `Ajustado B3` rows carry no trade code.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from typing import Any, ClassVar

import polars as pl

from fin.config import Zones
from fin.ingest.base import Connector, Mode, NotData, Parsed
from fin.ingest.fetch import FetchSpec
from fin.ingest.http import BROWSER_UA
from fin.ingest.snapshots import _calendar, today_brt  # pyright: ignore[reportPrivateUsage]
from fin.schema import Column, Contract, Rule
from fin.store.manifest import Manifest
from fin.store.raw import RawStore

MONEY = pl.Decimal(38, 12)

TRADE_COLUMNS = (
    "RptDt",
    "DtRef",
    "InstrumentType",
    "Issuer",
    "TckrSymb",
    "Quantity",
    "Price",
    "Vol",
    "Rate",
    "Origin",
    "TradeTime",
    "TradeDate",
    "TradeCode",
    "ISIN",
    "SettlementDt",
    "Situation",
    "IdSer",
)
SALEOFF_COLUMNS = (
    "RptDt",
    "DtRef",
    "TckrSymb",
    "RefDt",
    "OperationType",
    "SettlementMethod",
    "Quantity",
    "Volume",
)
STOCK_COLUMNS = (
    "RptDt",
    "DtRef",
    "TckrSymb",
    "QuantityIssued",
    "QuantityMarket",
    "QuantityDeposited",
    "VolumeMarket",
    "VolumeDeposited",
    "QuantityInstrument",
)

FI_TRADE = Contract(
    table="staging.b3_fixed_income.fi_trade",
    version=1,
    description="One trade of a registered fixed-income instrument (B3 BDI 'Negócio a negócio', OTC/Puma).",
    columns=(
        Column("ref_date", pl.Date, "RptDt: report date of the table", "data de referência", "date", False),
        Column("trade_date", pl.Date, "TradeDate: Data negócio", "data do negócio", "date", False),
        Column("instrument_type", pl.String, "InstrumentType: DEB, CRA, CRI, CFF, LIG, LF, COE...", "instrumento"),
        Column("issuer_name", pl.String, "Issuer as written", "emissor"),
        Column("ticker", pl.String, "TckrSymb: Código IF (B3/Cetip code)", "código IF", nullable=False),
        Column("quantity", MONEY, "Quantity traded", "quantidade negociada", "instruments"),
        Column("price_brl", MONEY, "Price: PU of the trade", "preço (PU) do negócio", "BRL per instrument"),
        Column("volume_brl", MONEY, "Vol: financial volume", "volume financeiro", "BRL"),
        Column(
            "rate_pct",
            MONEY,
            "Rate: Taxa negócio (unit not stated in the table; magnitudes are % a.a.)",
            "taxa do negócio",
            "% a.a. (assumed)",
        ),
        Column("origin", pl.String, "Origin: venue/mode (Pre-registro - Voice, Registro...)", "origem"),
        Column("trade_time", pl.String, "TradeTime HH:MM:SS (BRT, as published)", "horário", "HH:MM:SS"),
        Column(
            "trade_code",
            pl.String,
            "TradeCode: '#' + digits; null on 'Ajustado B3' rows (B3 adjustments)",
            "cód. do negócio",
        ),
        Column("isin", pl.String, "ISIN, when the table has one", "ISIN"),
        Column("settlement_date", pl.Date, "SettlementDt", "data de liquidação", "date"),
        Column("situation", pl.String, "Situation: Confirmado, Ajustado B3, Cancelado, Cancelado B3", "situação"),
        Column("series_id", pl.Int64, "IdSer (B3 series id)", "IdSer"),
    ),
    rules=(
        Rule("trade_on_report_date", pl.col("trade_date") == pl.col("ref_date")),
        Rule("quantity_positive", pl.col("quantity").is_null() | (pl.col("quantity") > 0)),
    ),
    key=("ref_date", "trade_code", "raw_sha256"),
)

FI_SETTLEMENT = Contract(
    table="staging.b3_fixed_income.fi_settlement",
    version=1,
    description="Settlement volume of an instrument type by operation type and method, per day (B3 BDI 'Liquidação').",
    columns=(
        Column("ref_date", pl.Date, "RptDt", "data de referência", "date", False),
        Column(
            "instrument_type", pl.String, "TckrSymb: instrument type (CDCA, CCB...)", "tipo de instrumento", "", False
        ),
        Column("operation_date", pl.Date, "RefDt: Data da operação", "data da operação", "date"),
        Column("operation_type", pl.String, "OperationType", "tipo de operação"),
        Column("settlement_method", pl.String, "SettlementMethod (BRUTA_STR, BRUTA_LIQUIDANTE...)", "modalidade"),
        Column("quantity", MONEY, "Quantity settled", "quantidade liquidada", "instruments"),
        Column("volume_brl", MONEY, "Volume", "volume financeiro", "BRL"),
    ),
    key=("ref_date", "instrument_type", "operation_date", "operation_type", "settlement_method", "raw_sha256"),
)

FI_STOCK = Contract(
    table="staging.b3_fixed_income.fi_stock",
    version=1,
    description="Stock of registered and deposited instruments by instrument type, per day (B3 BDI 'Estoque').",
    columns=(
        Column("ref_date", pl.Date, "RptDt", "data de referência", "date", False),
        Column("instrument_type", pl.String, "TckrSymb: instrument type", "tipo de instrumento", "", False),
        Column("quantity_issued", MONEY, "QuantityIssued", "quantidade emitida", "instruments"),
        Column("quantity_market", MONEY, "QuantityMarket", "quantidade em mercado", "instruments"),
        Column("quantity_deposited", MONEY, "QuantityDeposited", "quantidade depositada", "instruments"),
        Column("volume_market_brl", MONEY, "VolumeMarket", "volume em mercado", "BRL"),
        Column("volume_deposited_brl", MONEY, "VolumeDeposited", "volume depositado", "BRL"),
        Column(
            "instrument_count", MONEY, "QuantityInstrument: number of instruments", "número de instrumentos", "count"
        ),
    ),
    key=("ref_date", "instrument_type", "raw_sha256"),
)


class LayoutError(ValueError):
    pass


def _dec(x: Any) -> Decimal | None:
    if x is None:
        return None
    if isinstance(x, bool) or not isinstance(x, int | Decimal):
        raise LayoutError(f"not a number: {x!r}")
    d = Decimal(x)
    exp = d.as_tuple().exponent
    if isinstance(exp, int) and exp < -12:
        raise LayoutError(f"more than 12 decimals (a cast would round): {x!r}")
    return d


def _date(x: Any) -> date | None:
    if x is None:
        return None
    if not isinstance(x, str) or len(x) != 19 or not x.endswith("T00:00:00"):
        raise LayoutError(f"not a midnight timestamp: {x!r}")
    return date.fromisoformat(x[:10])


def _table(blob: bytes, expected: tuple[str, ...]) -> list[list[Any]]:
    try:
        doc = json.loads(blob, parse_float=Decimal)
    except ValueError as e:
        raise NotData(f"not JSON: {e}") from e
    table = doc.get("table") if isinstance(doc, dict) else None
    if not isinstance(table, dict) or "columns" not in table:
        raise NotData("no `table.columns` in the answer")
    names = tuple(c["name"] for c in table["columns"])
    if names != expected:
        raise LayoutError(f"columns changed: {names} != {expected}")
    rows = table.get("values") or []
    if any(len(r) != len(expected) for r in rows):
        raise LayoutError("a row's width differs from the header")
    return rows


def _frame(rows: list[dict[str, Any]], contract: Contract, row: dict[str, Any]) -> pl.DataFrame:
    schema = {c.name: c.dtype for c in contract.columns} | {"raw_locator": pl.String}
    df = pl.DataFrame(rows, schema=schema, orient="row")
    return df.with_columns(
        pl.lit(row["raw_sha256"]).alias("raw_sha256"), pl.lit(row["ingest_run_id"]).alias("ingest_run_id")
    )


def _locator(row: dict[str, Any]) -> str:
    return str(row.get("notes") or "page=1")


def parse_trade(blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
    loc = _locator(row)
    out: list[dict[str, Any]] = []
    for i, r in enumerate(_table(blob, TRADE_COLUMNS)):
        v = dict(zip(TRADE_COLUMNS, r, strict=True))
        if v["DtRef"] != v["RptDt"]:
            raise LayoutError(f"DtRef != RptDt in row {i}: {v['DtRef']!r} vs {v['RptDt']!r}")
        out.append(
            {
                "ref_date": _date(v["RptDt"]),
                "trade_date": _date(v["TradeDate"]),
                "instrument_type": v["InstrumentType"],
                "issuer_name": v["Issuer"],
                "ticker": v["TckrSymb"],
                "quantity": _dec(v["Quantity"]),
                "price_brl": _dec(v["Price"]),
                "volume_brl": _dec(v["Vol"]),
                "rate_pct": _dec(v["Rate"]),
                "origin": v["Origin"],
                "trade_time": v["TradeTime"],
                "trade_code": v["TradeCode"],
                "isin": v["ISIN"],
                "settlement_date": _date(v["SettlementDt"]),
                "situation": v["Situation"],
                "series_id": v["IdSer"],
                "raw_locator": f"{loc}|row={i}",
            }
        )
    df = _frame(out, FI_TRADE, row)
    for (d,), part in df.partition_by("ref_date", as_dict=True, maintain_order=True).items():
        yield Parsed("fi_trade", f"ref_date={d}", part)


def parse_settlement(blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
    loc = _locator(row)
    out: list[dict[str, Any]] = []
    for i, r in enumerate(_table(blob, SALEOFF_COLUMNS)):
        v = dict(zip(SALEOFF_COLUMNS, r, strict=True))
        if v["DtRef"] != v["RptDt"]:
            raise LayoutError(f"DtRef != RptDt in row {i}")
        out.append(
            {
                "ref_date": _date(v["RptDt"]),
                "instrument_type": v["TckrSymb"],
                "operation_date": _date(v["RefDt"]),
                "operation_type": v["OperationType"],
                "settlement_method": v["SettlementMethod"],
                "quantity": _dec(v["Quantity"]),
                "volume_brl": _dec(v["Volume"]),
                "raw_locator": f"{loc}|row={i}",
            }
        )
    df = _frame(out, FI_SETTLEMENT, row)
    for (d,), part in df.partition_by("ref_date", as_dict=True, maintain_order=True).items():
        yield Parsed("fi_settlement", f"ref_date={d}", part)


def parse_stock(blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
    loc = _locator(row)
    out: list[dict[str, Any]] = []
    for i, r in enumerate(_table(blob, STOCK_COLUMNS)):
        v = dict(zip(STOCK_COLUMNS, r, strict=True))
        if v["DtRef"] != v["RptDt"]:
            raise LayoutError(f"DtRef != RptDt in row {i}")
        out.append(
            {
                "ref_date": _date(v["RptDt"]),
                "instrument_type": v["TckrSymb"],
                "quantity_issued": _dec(v["QuantityIssued"]),
                "quantity_market": _dec(v["QuantityMarket"]),
                "quantity_deposited": _dec(v["QuantityDeposited"]),
                "volume_market_brl": _dec(v["VolumeMarket"]),
                "volume_deposited_brl": _dec(v["VolumeDeposited"]),
                "instrument_count": _dec(v["QuantityInstrument"]),
                "raw_locator": f"{loc}|row={i}",
            }
        )
    df = _frame(out, FI_STOCK, row)
    for (d,), part in df.partition_by("ref_date", as_dict=True, maintain_order=True).items():
        yield Parsed("fi_stock", f"ref_date={d}", part)


PARSERS = {"Trade": parse_trade, "SaleOff": parse_settlement, "Stock": parse_stock}


class B3FixedIncome(Connector):
    """BDI fixed-income tables with history (see the module docstring). Backfill: every business day since the first
    one served, page by page; incremental: the last 10 business days, the last 2 re-fetched for late corrections.
    A day whose pages are not all archived (an interrupted run) is completed, never skipped."""

    source_id: ClassVar[str] = "b3_fixed_income"
    version: ClassVar[str] = "1"
    user_agent: ClassVar[str | None] = BROWSER_UA  # B3 hosts sit behind Cloudflare
    min_interval: ClassVar[float] = 0.4
    concurrency: ClassVar[int] = 2
    contracts: ClassVar[dict[str, Contract]] = {
        "fi_trade": FI_TRADE,
        "fi_settlement": FI_SETTLEMENT,
        "fi_stock": FI_STOCK,
    }
    BASE = "https://drp.b3.com.br/bdi/table"
    TAKE = 1000  # 1500, 2000 and 5000 answer HTTP 400 (measured 2026-11-08)
    FIRST: ClassVar[dict[str, date]] = {
        "Trade": date(2023, 3, 13),
        "SaleOff": date(2023, 3, 1),
        "Stock": date(2023, 3, 1),
    }
    LOOKBACK = 10
    REFRESH = 2

    def _spec(self, table: str, d: date, page: int) -> FetchSpec:
        return FetchSpec(
            self.source_id,
            table,
            f"{self.BASE}/{table}/{d:%Y-%m-%d}/{d:%Y-%m-%d}/{page}/{self.TAKE}",
            "json",
            method="POST",
            json={},
            reference_date=d,
            conditional=False,
            locator=f"page={page}",
        )

    def parse(self, blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
        return PARSERS[row["dataset_id"]](blob, row)

    def _manifest(self, zones: Zones, table: str) -> pl.DataFrame:
        m = Manifest(zones.manifest).read()
        if m.is_empty():
            return m
        return m.filter(
            (pl.col("source_id") == self.source_id)
            & (pl.col("dataset_id") == table)
            & (pl.col("http_status") == 200)
            & pl.col("source_reference_date").is_not_null()
        )

    @staticmethod
    def _held(m: pl.DataFrame) -> dict[date, set[str]]:
        out: dict[date, set[str]] = {}
        if m.is_empty():
            return out
        for d, loc in zip(m["source_reference_date"].to_list(), m["notes"].to_list(), strict=True):
            out.setdefault(d, set()).add(loc or "page=1")
        return out

    @staticmethod
    def _page_count(raw: RawStore, m: pl.DataFrame, d: date) -> int:
        """`pageCount` of the day, from its archived first page (a day with no first page is fetched from it)."""
        first = m.filter((pl.col("source_reference_date") == d) & (pl.col("notes") == "page=1"))
        if first.is_empty():
            return 1
        blob = raw.read(first.sort("fetched_at")["raw_sha256"][-1])
        return int(json.loads(blob).get("table", {}).get("pageCount") or 1)

    def discover(self, mode: Mode, zones: Zones, **options: Any) -> Iterable[FetchSpec]:
        raw = RawStore(zones.raw)
        cal = _calendar(zones)
        end = cal.preceding(today_brt())
        recent = cal.business_days(cal.add_business_days(end, -(self.LOOKBACK - 1)), end)
        for table, first in self.FIRST.items():
            days = cal.business_days(first, end) if mode is Mode.BACKFILL else recent
            m = self._manifest(zones, table)
            held = self._held(m)
            refresh = set(recent[-self.REFRESH :])
            for d in reversed(days):  # newest first: the days most likely to be asked for come in first
                have = held.get(d, set())
                if d in refresh or "page=1" not in have:
                    yield self._spec(table, d, 1)
                    continue
                pages = self._page_count(raw, m, d)
                for p in range(2, pages + 1):
                    if f"page={p}" not in have:
                        yield self._spec(table, d, p)

    def follow(self, spec: FetchSpec, blob: bytes) -> Iterable[FetchSpec]:
        if spec.locator != "page=1" or spec.reference_date is None:
            return ()
        pages = int(json.loads(blob).get("table", {}).get("pageCount") or 1)
        return [self._spec(spec.dataset_id, spec.reference_date, p) for p in range(2, pages + 1)]
