"""BCB PTAX exchange rates (Olinda OData) -> staging `quote`, `currency` and long series (docs/sources/bcb_ptax.md).

One request per currency returns every bulletin since 1984 (`CotacaoMoedaPeriodo`): Abertura, Intermediário (up to
~13 a day in the 1990s), Fechamento (the PTAX proper) and, 1999-2011, Fechamento Interbancário. The USD-only
`CotacaoDolarPeriodo` is exactly the USD Fechamento rows of that response (measured 2026-11-07: 10,505 identical rows),
so it is parsed (dataset `dolar_period`) but never fetched: storage stays lean.

Staging, source-shaped:
- `quote`: one bulletin of one currency; rates exact (JSON numbers read as decimals, never floats). `parity_*` is
  the currency's own quotation against the US dollar (type A: currency units per USD; type B: USD per currency
  unit, see `currency.quote_type`); `brl_*` is BRL per ONE unit of the currency, as published. Values are not
  rebased across the old Brazilian currencies (cruzeiro ... real, 1994-07-01).
- `currency`: the `Moedas` list (symbol, name, quote type).
- `observation`/`definition` (shared contracts of ingest/series.py): the Fechamento (PTAX) buy and sell rates as
  `bcb_ptax:<CCY>:buy|sell`, daily; on the 9 days with two Fechamento rows the later one is the day's value.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, ClassVar

import polars as pl

from fin.config import Zones
from fin.ingest import series
from fin.ingest.base import Connector, Mode, Parsed
from fin.ingest.fetch import FetchSpec
from fin.ingest.snapshots import held_rows, today_brt
from fin.schema import Column, Contract, Rule
from fin.store.runs import IngestRun

BASE = "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
PERIOD = "CotacaoMoedaPeriodo(moeda=@moeda,dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)"
FIRST_DATE = date(1984, 1, 1)  # earliest quote served: 1984-11-29
INCREMENTAL_DAYS = 30
RATE = pl.Decimal(38, 12)
CLOSE = "Fechamento"


class LayoutError(ValueError):
    pass


QUOTE = Contract(
    table="staging.bcb_ptax.quote",
    version=1,
    description="One PTAX bulletin of one currency, as the Olinda API publishes it (not rebased across currencies).",
    columns=(
        Column("currency", pl.String, "ISO-like symbol (USD, EUR, JPY...)", "moeda", nullable=False),
        Column(
            "bulletin",
            pl.String,
            "tipoBoletim: Abertura, Intermediário, Fechamento (the PTAX), Fechamento Interbancário",
            "boletim",
            nullable=False,
        ),
        Column("quote_date", pl.Date, "date of the quote (from dataHoraCotacao)", "data", "date", nullable=False),
        Column(
            "quoted_at",
            pl.Datetime("us"),
            "dataHoraCotacao as published: Brasília local time, no zone",
            "data e hora da cotação",
            "timestamp (BRT, naive)",
            nullable=False,
        ),
        Column(
            "parity_buy",
            RATE,
            "paridadeCompra: currency units per USD (type A) or USD per unit (type B); null on the USD-only endpoint",
            "paridade de compra",
            "currency pair as per currency.quote_type",
        ),
        Column("parity_sell", RATE, "paridadeVenda", "paridade de venda", "currency pair as per currency.quote_type"),
        Column("brl_buy", RATE, "cotacaoCompra: BRL per 1 unit of the currency", "cotação de compra", "BRL per unit"),
        Column("brl_sell", RATE, "cotacaoVenda: BRL per 1 unit of the currency", "cotação de venda", "BRL per unit"),
    ),
    rules=(
        Rule("brl_rates_positive", (pl.col("brl_buy") > 0) & (pl.col("brl_sell") > 0)),
        Rule("quote_date_matches_timestamp", pl.col("quote_date") == pl.col("quoted_at").dt.date()),
    ),
    key=("currency", "bulletin", "quoted_at", "raw_sha256"),
)

CURRENCY = Contract(
    table="staging.bcb_ptax.currency",
    version=1,
    description="The currencies PTAX is published for (the Moedas entity), with the quotation convention of each.",
    columns=(
        Column("symbol", pl.String, "simbolo", "símbolo", nullable=False),
        Column("name", pl.String, "nomeFormatado (pt-BR)", "nome", nullable=False),
        Column(
            "quote_type",
            pl.String,
            "tipoMoeda: A = currency units per USD, B = USD per currency unit (parity convention)",
            "tipo de cotação",
            nullable=False,
        ),
    ),
    rules=(Rule("quote_type_known", pl.col("quote_type").is_in(["A", "B"])),),
    key=("symbol", "raw_sha256"),
)

CONTRACTS: dict[str, Contract] = {
    "quote": QUOTE,
    "currency": CURRENCY,
    "observation": series.OBSERVATION,
    "definition": series.DEFINITION,
}

_QUOTE_IN = {
    "currency": pl.String,
    "bulletin": pl.String,
    "quote_date": pl.Date,
    "quoted_at": pl.Datetime("us"),
    "parity_buy": pl.Decimal(38, 12),
    "parity_sell": pl.Decimal(38, 12),
    "brl_buy": pl.Decimal(38, 12),
    "brl_sell": pl.Decimal(38, 12),
    "raw_locator": pl.String,
}


def _rate(v: Any, where: str) -> Decimal | None:
    if v is None:
        return None
    if not isinstance(v, Decimal):
        raise LayoutError(f"{where}: expected a JSON number, got {v!r}")
    if -v.as_tuple().exponent > 12:  # type: ignore[operator]
        raise LayoutError(f"{where}: {v} has more than 12 decimals")
    return v


def _doc(blob: bytes) -> list[dict[str, Any]]:
    doc = json.loads(blob, parse_float=Decimal, parse_int=Decimal)
    if not isinstance(doc, dict) or "value" not in doc:
        raise LayoutError("PTAX: no 'value' array in the response")
    return list(doc["value"])


def _currency_of(dataset_id: str) -> str:
    if dataset_id == "dolar_period":
        return "USD"
    if dataset_id.startswith("period_"):
        return dataset_id.removeprefix("period_")
    raise LayoutError(f"PTAX: unknown dataset {dataset_id!r}")


def parse_quotes(blob: bytes, row: dict[str, Any]) -> pl.DataFrame:
    """`CotacaoMoedaPeriodo`: {paridadeCompra, paridadeVenda, cotacaoCompra, cotacaoVenda, dataHoraCotacao,
    tipoBoletim}; `CotacaoDolarPeriodo`: the same without parities and bulletin (always the closing PTAX)."""
    ccy = _currency_of(str(row["dataset_id"]))
    rows: list[dict[str, Any]] = []
    for i, r in enumerate(_doc(blob)):
        where = f"{ccy} $.value[{i}]"
        try:
            at = datetime.fromisoformat(r["dataHoraCotacao"])
            buy, sell = _rate(r["cotacaoCompra"], where), _rate(r["cotacaoVenda"], where)
        except KeyError as e:
            raise LayoutError(f"{where}: missing key {e}") from e
        rows.append(
            {
                "currency": ccy,
                "bulletin": r.get("tipoBoletim", CLOSE),
                "quote_date": at.date(),
                "quoted_at": at,
                "parity_buy": _rate(r.get("paridadeCompra"), where),
                "parity_sell": _rate(r.get("paridadeVenda"), where),
                "brl_buy": buy,
                "brl_sell": sell,
                "raw_locator": f"$.value[{i}]",
            }
        )
    df = pl.DataFrame(rows, schema=_QUOTE_IN, orient="row")
    return df.with_columns(
        pl.lit(row["raw_sha256"]).alias("raw_sha256"), pl.lit(row["ingest_run_id"]).alias("ingest_run_id")
    )


def parse_currencies(blob: bytes, row: dict[str, Any]) -> pl.DataFrame:
    rows = [
        {
            "symbol": r["simbolo"],
            "name": r["nomeFormatado"],
            "quote_type": r["tipoMoeda"],
            "raw_locator": f"$.value[{i}]",
        }
        for i, r in enumerate(_doc(blob))
    ]
    df = pl.DataFrame(
        rows, schema=dict.fromkeys(("symbol", "name", "quote_type", "raw_locator"), pl.String), orient="row"
    )
    return df.with_columns(
        pl.lit(row["raw_sha256"]).alias("raw_sha256"), pl.lit(row["ingest_run_id"]).alias("ingest_run_id")
    )


SIDES = (("buy", "brl_buy", "compra"), ("sell", "brl_sell", "venda"))


def parse_series(quotes: pl.DataFrame, row: dict[str, Any]) -> tuple[pl.DataFrame, pl.DataFrame]:
    """The Fechamento (PTAX) rates as series: the last quote of each day."""
    ccy = quotes["currency"][0]
    close = quotes.filter(pl.col("bulletin") == CLOSE).sort("quoted_at").unique("quote_date", keep="last")
    close = close.sort("quote_date")
    prov = [
        pl.lit(row["raw_sha256"]).alias("raw_sha256"),
        pl.lit(row["ingest_run_id"]).alias("ingest_run_id"),
        pl.lit(row["fetched_at"], dtype=series.KT).alias("kt_first_seen_at"),
    ]
    parts: list[pl.DataFrame] = []
    for side, col, _ in SIDES:
        parts.append(
            close.select(
                pl.lit(f"bcb_ptax:{ccy}:{side}").alias("series_id"),
                pl.col("quote_date").alias("vt_date"),
                pl.lit(None, dtype=pl.Date).alias("vt_until"),
                pl.col("quote_date").dt.strftime("%Y-%m-%d").alias("period_text"),
                pl.col(col).cast(series.VALUE).alias("value"),
                pl.col(col).cast(pl.String).alias("value_text"),
                pl.lit(None, dtype=pl.String).alias("missing_reason"),
                pl.col("raw_locator"),
            )
        )
    obs = pl.concat(parts).with_columns(*prov)
    defs = pl.DataFrame(
        [
            {
                "series_id": f"bcb_ptax:{ccy}:{side}",
                "source_code": f"{ccy}:{side}",
                "name": f"PTAX {ccy} fechamento, {pt} (CotacaoMoedaPeriodo)",
                "frequency": "D",
                "frequency_text": "diária",
                "unit": f"BRL per 1 {ccy}, as published (not rebased across currency changes)",
                "raw_locator": "$.value",
            }
            for side, _, pt in SIDES
        ],
        schema=dict.fromkeys(
            ("series_id", "source_code", "name", "frequency", "frequency_text", "unit", "raw_locator"), pl.String
        ),
    ).with_columns(*prov)
    return obs, defs


def parse_payload(blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
    ds = str(row["dataset_id"])
    if ds == "moedas":
        yield Parsed("currency", "all", parse_currencies(blob, row))
        return
    quotes = parse_quotes(blob, row)
    part = f"currency={_currency_of(ds)}"
    yield Parsed("quote", part, quotes)
    if quotes.height:
        obs, defs = parse_series(quotes, row)
        yield Parsed("observation", part, obs)
        yield Parsed("definition", part, defs)


def _mdy(d: date) -> str:
    return f"'{d:%m-%d-%Y}'"


class BcbPtax(Connector):
    source_id: ClassVar[str] = "bcb_ptax"
    version: ClassVar[str] = "1"
    contracts: ClassVar[dict[str, Contract]] = CONTRACTS
    dedup_staging: ClassVar[bool] = True
    _mode: Mode = Mode.INCREMENTAL
    _zones: Zones | None = None

    def discover(self, mode: Mode, zones: Zones, **options: Any) -> Iterable[FetchSpec]:
        """The currency list first; `follow` then asks for each currency listed (so a new one is never missed)."""
        self._mode, self._zones = mode, zones
        yield FetchSpec(
            self.source_id,
            "moedas",
            BASE + "Moedas",
            "json",
            params={"$format": "json"},
            reference_date=today_brt(),
            conditional=False,
            min_bytes=50,
        )

    def _window(self, symbol: str, today: date) -> tuple[date, bool]:
        """Start of the request and whether it is the incremental window. Everything the first time (or on
        backfill); afterwards the last 30 days, reaching back to a week before the previous fetch if that was older."""
        if self._mode is Mode.BACKFILL or self._zones is None:
            return FIRST_DATE, False
        held = held_rows(self._zones, self.source_id, f"period_{symbol}")
        if held.is_empty():
            return FIRST_DATE, False
        last = max(at.date() for at in held["fetched_at"].to_list())
        start = min(today - timedelta(days=INCREMENTAL_DAYS), last - timedelta(days=7))
        return (FIRST_DATE, False) if start < today - timedelta(days=365) else (start, True)

    def follow(self, spec: FetchSpec, blob: bytes) -> Iterable[FetchSpec]:
        if spec.dataset_id != "moedas":
            return ()
        today = today_brt()
        out: list[FetchSpec] = []
        for sym in sorted(c["simbolo"] for c in _doc(blob)):
            start, since = self._window(sym, today)
            out.append(
                FetchSpec(
                    self.source_id,
                    f"period_{sym}",
                    BASE + PERIOD,
                    "json",
                    params={
                        "@moeda": f"'{sym}'",
                        "@dataInicial": _mdy(start),
                        "@dataFinalCotacao": _mdy(today),
                        "$format": "json",
                    },
                    reference_date=today,
                    conditional=False,
                    min_bytes=50,
                    locator=f"{sym}|since" if since else sym,
                )
            )
        return out

    def parse(self, blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
        return parse_payload(blob, row)

    def derive(self, zones: Zones, run: IngestRun) -> None:
        series.build_core(zones, self.source_id, run)
