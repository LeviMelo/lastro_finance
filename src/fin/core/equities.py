"""Exchange-traded instruments and their daily prices from COTAHIST (PLAN §4.3.2, §4.3.4, §4.4; ADR-0015).

Core tables, rebuilt from staging `b3_cotahist/quote`:
- `instrument`: one row per instrument, with a stable surrogate `instrument_id` (`I` + 12 hex of SHA-256 of its
  primary identifier), first/last trade date, and the latest short name, specification and BDI code seen.
- `instrument_identifier`: time-ranged identifiers (ISIN, B3_CODISI, TICKER) with the method that linked them.
- `price_daily`: spot (`lote_padrao`, TPMERC 10) and odd-lot (`fracionario`, 20) sessions, prices **per one unit**
  in the currency of the day (quoted ÷ FATCOT, exact), with the exact fraction that converts that currency to BRL.

Identity rules (v1):
1. An instrument is an ISIN. Before 1995-05-15 (and for a few later rows) CODISI holds B3's internal code.
2. An internal code is the same instrument as an ISIN when one ticker trades under the code and, on its next trading
   day, under the ISIN, and the pair is one-to-one. Otherwise it stays an instrument of its own.
3. ISIN changes of one security (conversions, some restructurings) are distinct instruments here; corporate events
   link them later (PLAN §4.3.3).
4. A ticker is an attribute valid over the dates it traded under that instrument; it can be reused later.

Currencies before the Real are resolved by date, not by MODREF (COTAHIST writes `CR$` for both the 1990 Cruzeiro and
the 1993 Cruzeiro Real). Each changeover was checked in the data: the median price ratio across 1989-01, 1993-08 and
1994-07 is 1,033, 1,002 and 2,744 (docs/evaluation/2026-11-07-storage-and-price-daily.md).
"""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

import polars as pl

from fin.config import Zones
from fin.schema import Column, Contract, Rule
from fin.store.runs import IngestRun
from fin.store.tables import write_parquet

UNIT_PRICE = pl.Decimal(38, 12)
ISIN_RE = r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$"
SEGMENTS = {10: "lote_padrao", 20: "fracionario"}

# (first day, ISO 4217 code, BRL per unit as numerator/denominator): Decreto-Lei 2.283/1986 (CZ$ = 1,000 Cr$),
# Lei 7.730/1989 (NCz$ = 1,000 CZ$), Lei 8.024/1990 (Cr$ = NCz$), Lei 8.697/1993 (CR$ = 1,000 Cr$),
# Lei 8.880/1994 (R$ = 2,750 CR$). Verified on COTAHIST price ratios across each date (see module docstring).
CURRENCIES: tuple[tuple[date, str, int, int], ...] = (
    (date(1900, 1, 1), "BRB", 1, 2_750_000_000_000),  # Cruzeiro (until 1986-02-27)
    (date(1986, 2, 28), "BRC", 1, 2_750_000_000),  # Cruzado
    (date(1989, 1, 16), "BRN", 1, 2_750_000),  # Cruzado Novo
    (date(1990, 3, 16), "BRE", 1, 2_750_000),  # Cruzeiro
    (date(1993, 8, 1), "BRR", 1, 2_750),  # Cruzeiro Real
    (date(1994, 7, 1), "BRL", 1, 1),  # Real
)

INSTRUMENT = Contract(
    table="core.instrument",
    version=1,
    description="An exchange-traded instrument, identified by our surrogate id (ADR-0015).",
    provenance=False,
    columns=(
        Column(
            "instrument_id",
            pl.String,
            "surrogate id: I + 12 hex of sha256(primary)",
            "id do instrumento",
            nullable=False,
        ),
        Column("primary_scheme", pl.String, "ISIN or B3_CODISI", "esquema primário", nullable=False),
        Column("primary_value", pl.String, "the primary identifier", "identificador primário", nullable=False),
        Column("first_trade", pl.Date, "first session in COTAHIST", "primeiro pregão", "date", nullable=False),
        Column("last_trade", pl.Date, "last session in COTAHIST", "último pregão", "date", nullable=False),
        Column("short_name", pl.String, "NOMRES on the last session", "nome resumido"),
        Column("especi", pl.String, "ESPECI on the last session (ON, PN, UNT, CI…)", "especificação"),
        Column("codbdi", pl.String, "CODBDI of the last standard-lot session (else odd lot)", "código BDI"),
        Column(
            "asset_class",
            pl.String,
            "share, unit, fund_quota (FII/ETF), bdr, right, other (provisional)",
            "classe de ativo",
            nullable=False,
        ),
    ),
    key=("instrument_id",),
)

IDENTIFIER = Contract(
    table="core.instrument_identifier",
    version=1,
    description="A time-ranged identifier of an instrument (SCD type 2).",
    provenance=False,
    columns=(
        Column("instrument_id", pl.String, "surrogate id", "id do instrumento", nullable=False),
        Column("scheme", pl.String, "ISIN, B3_CODISI or TICKER", "esquema", nullable=False),
        Column("value", pl.String, "identifier as written by B3", "valor", nullable=False),
        Column("vt_from", pl.Date, "first session with this identifier", "válido de", "date", nullable=False),
        Column("vt_to", pl.Date, "last session with this identifier (inclusive)", "válido até", "date", nullable=False),
        Column(
            "method", pl.String, "how it was linked (cotahist_isin, cotahist_code_to_isin)", "método", nullable=False
        ),
        Column("source_id", pl.String, "b3_cotahist", "fonte", nullable=False),
    ),
    rules=(Rule("range_ordered", pl.col("vt_from") <= pl.col("vt_to")),),
    key=("instrument_id", "scheme", "value", "vt_from"),
)

_P = "price per one unit, in `currency` (quoted ÷ quote_factor)"
PRICE_DAILY = Contract(
    table="core.price_daily",
    version=1,
    description="One instrument's session in one market segment: raw, unadjusted, per one unit (PLAN §4.3.4).",
    columns=(
        Column("instrument_id", pl.String, "surrogate id", "id do instrumento", nullable=False),
        Column("trade_date", pl.Date, "session date", "data do pregão", "date", nullable=False),
        Column("market_segment", pl.String, "lote_padrao or fracionario", "segmento", nullable=False),
        Column("ticker", pl.String, "trading code on that date", "código de negociação", nullable=False),
        Column("currency", pl.String, "ISO 4217 of the day: BRB, BRC, BRN, BRE, BRR or BRL", "moeda", nullable=False),
        *(
            Column(n, UNIT_PRICE, _P, pt, "`currency` per unit")
            for n, pt in (
                ("open", "abertura"),
                ("high", "máxima"),
                ("low", "mínima"),
                ("close", "fechamento"),
                ("avg", "preço médio"),
                ("best_bid", "melhor oferta de compra"),
                ("best_ask", "melhor oferta de venda"),
            )
        ),
        Column("n_trades", pl.Int64, "number of trades", "negócios", "count"),
        Column("qty", pl.Int64, "units traded", "quantidade", "units"),
        Column("volume", pl.Decimal(20, 2), "traded value", "volume financeiro", "`currency`"),
        Column(
            "quote_factor",
            pl.Int32,
            "FATCOT: B3 quoted prices per this many units",
            "fator de cotação",
            "units",
            nullable=False,
        ),
        Column(
            "distribution_number",
            pl.Int16,
            "DISMES: changes at each corporate event",
            "número de distribuição",
            "ordinal",
            nullable=False,
        ),
        Column(
            "brl_num",
            pl.Int64,
            "BRL per unit of `currency` = brl_num / brl_den",
            "fator BRL (numerador)",
            "BRL per currency unit (numerator)",
            nullable=False,
        ),
        Column(
            "brl_den",
            pl.Int64,
            "see brl_num",
            "fator BRL (denominador)",
            "BRL per currency unit (denominator)",
            nullable=False,
        ),  # fmt: skip
    ),
    rules=(
        Rule("segment_known", pl.col("market_segment").is_in(list(SEGMENTS.values()))),
        Rule("low_le_high", pl.col("low") <= pl.col("high")),
    ),
    key=("instrument_id", "trade_date", "market_segment", "ticker"),
)


def instrument_id(primary: str) -> str:
    return "I" + hashlib.sha256(primary.encode("utf-8")).hexdigest()[:12]


def _quotes(staging: Path) -> pl.LazyFrame:
    q = pl.scan_parquet(staging / "b3_cotahist" / "quote" / "**" / "*.parquet", hive_partitioning=False)
    return q.filter(pl.col("tpmerc").is_in(list(SEGMENTS)))


def dedupe(q: pl.DataFrame) -> tuple[pl.DataFrame, int]:
    """One row per (date, ticker, market): the yearly file's row where the daily file repeats it. Returns the rows
    and the number of keys whose copies disagree (reported, never resolved silently)."""
    k = ["trade_date", "ticker", "tpmerc"]
    yearly = pl.col("raw_locator").str.starts_with("member=COTAHIST_A")
    q = q.with_columns(yearly.alias("_yearly")).sort(
        [*k, "_yearly", "raw_sha256"], descending=[False] * 3 + [True, False]
    )
    conflicts = q.group_by(k).agg(pl.col("close").n_unique().alias("n")).filter(pl.col("n") > 1).height
    return q.unique(k, keep="first", maintain_order=True).drop("_yearly"), conflicts


def link_codes(q: pl.DataFrame) -> dict[str, str]:
    """B3 internal code -> ISIN, when one ticker steps from the code to the ISIN on consecutive sessions and the pair
    is one-to-one."""
    seq = (
        q.select("ticker", "trade_date", "isin")
        .unique()
        .sort("ticker", "trade_date")
        .with_columns(pl.col("isin").shift(1).over("ticker").alias("prev"))
        .filter(
            pl.col("prev").is_not_null()
            & (pl.col("prev") != pl.col("isin"))
            & ~pl.col("prev").str.contains(ISIN_RE)
            & pl.col("isin").str.contains(ISIN_RE)
        )
        .select(pl.col("prev").alias("code"), "isin")
        .unique()
    )
    one = seq.filter((pl.len().over("code") == 1) & (pl.len().over("isin") == 1))
    return dict(one.iter_rows())


def _asset_class(especi: pl.Expr, codbdi: pl.Expr) -> pl.Expr:
    e = especi.fill_null("")
    return (
        pl.when(codbdi == "12").then(pl.lit("fund_quota"))
        .when(e.str.starts_with("CI")).then(pl.lit("fund_quota"))
        .when(e.str.starts_with("UNT")).then(pl.lit("unit"))
        .when(e.str.starts_with("DR")).then(pl.lit("bdr"))
        .when(e.str.contains(r"^(ON|PN|PNA|PNB|PNC|PND|PNE|PNF|PNG|PNH|PR|OR)\b")).then(pl.lit("share"))
        .when(e.str.contains(r"^(DIR|REC|BDR)")).then(pl.lit("right"))
        .otherwise(pl.lit("other"))
    )  # fmt: skip


def _currency() -> list[pl.Expr]:
    d = pl.col("trade_date")
    code = pl.lit(CURRENCIES[0][1])
    num = pl.lit(CURRENCIES[0][2], dtype=pl.Int64)
    den = pl.lit(CURRENCIES[0][3], dtype=pl.Int64)
    for start, c, n, m in CURRENCIES[1:]:
        code = pl.when(d >= start).then(pl.lit(c)).otherwise(code)
        num = pl.when(d >= start).then(pl.lit(n, dtype=pl.Int64)).otherwise(num)
        den = pl.when(d >= start).then(pl.lit(m, dtype=pl.Int64)).otherwise(den)
    return [code.alias("currency"), num.alias("brl_num"), den.alias("brl_den")]


def build(zones: Zones, run: IngestRun | None = None) -> dict[str, int]:
    raw_q = _quotes(zones.staging).collect()
    if raw_q.is_empty():
        return {}
    q, conflicts = dedupe(raw_q)
    links = link_codes(q)
    q = q.with_columns(
        pl.col("isin").replace(links).alias("primary"),
        pl.when(pl.col("isin").str.contains(ISIN_RE))
        .then(pl.lit("ISIN"))
        .otherwise(pl.lit("B3_CODISI"))
        .alias("_scheme"),
    )
    ids = (
        q.select("primary")
        .unique()
        .with_columns(pl.col("primary").map_elements(instrument_id, return_dtype=pl.String).alias("instrument_id"))
    )
    q = q.join(ids, on="primary", how="left")

    last = (
        q.sort("trade_date", "tpmerc")
        .group_by("instrument_id")
        .agg(
            pl.col("trade_date").min().alias("first_trade"),
            pl.col("trade_date").max().alias("last_trade"),
            pl.col("short_name").last(),
            pl.col("especi").last(),
            pl.col("codbdi").filter(pl.col("tpmerc") == 10).last().fill_null(pl.col("codbdi").last()).alias("codbdi"),
            pl.col("primary").first(),
            pl.col("codbdi").eq("12").any().alias("_fii"),
        )
    )
    instrument = last.with_columns(
        pl.when(pl.col("primary").str.contains(ISIN_RE)).then(pl.lit("ISIN")).otherwise(pl.lit("B3_CODISI"))
        .alias("primary_scheme"),
        pl.col("primary").alias("primary_value"),
        pl.when(pl.col("_fii")).then(pl.lit("fund_quota")).otherwise(_asset_class(pl.col("especi"), pl.col("codbdi")))
        .alias("asset_class"),
    ).select(INSTRUMENT.names).sort("instrument_id")  # fmt: skip

    def ranges(scheme: pl.Expr, value: str, method: pl.Expr) -> pl.DataFrame:
        return (
            q.group_by("instrument_id", value)
            .agg(pl.col("trade_date").min().alias("vt_from"), pl.col("trade_date").max().alias("vt_to"),
                 pl.col("_scheme").first())
            .with_columns(scheme.alias("scheme"), pl.col(value).alias("value"), method.alias("method"),
                          pl.lit("b3_cotahist").alias("source_id"))
            .select(IDENTIFIER.names)
        )  # fmt: skip

    linked = pl.col("value").is_in(list(links))
    codes = ranges(pl.col("_scheme"), "isin", pl.lit("cotahist_isin"))
    codes = codes.with_columns(
        pl.when(linked).then(pl.lit("cotahist_code_to_isin")).otherwise(pl.col("method")).alias("method")
    )
    tickers = ranges(pl.lit("TICKER"), "ticker", pl.lit("cotahist_isin"))
    identifier = pl.concat([codes, tickers]).sort("instrument_id", "scheme", "vt_from")

    price = q.with_columns(
        pl.col("tpmerc").replace_strict(SEGMENTS, return_dtype=pl.String).alias("market_segment"),
        *[
            (pl.col(c).cast(UNIT_PRICE) / pl.col("fatcot").cast(UNIT_PRICE)).cast(UNIT_PRICE).alias(c)
            for c in ("open", "high", "low", "close", "avg", "best_bid", "best_ask")
        ],
        pl.col("fatcot").alias("quote_factor"),
        pl.col("dismes").alias("distribution_number"),
        *_currency(),
    ).select(PRICE_DAILY.names)

    out: dict[str, int] = {"conflicting_copies": conflicts, "linked_codes": len(links)}
    for name, contract, frame in (
        ("instrument", INSTRUMENT, instrument),
        ("instrument_identifier", IDENTIFIER, identifier),
    ):
        good, bad = contract.split(frame)
        write_parquet(good, zones.core / name / f"{name}.parquet")
        out[name] = good.height
        out[f"{name}:quarantined"] = bad.height
    good, bad = PRICE_DAILY.split(price)
    target = zones.core / "price_daily"
    for (year,), part in good.group_by(pl.col("trade_date").dt.year()):
        write_parquet(part.sort("instrument_id", "trade_date", "market_segment"), target / f"year={year}.parquet")
    q_path = zones.quarantine / "core" / "price_daily.parquet"
    if bad.height:
        write_parquet(bad, q_path)
    else:
        q_path.unlink(missing_ok=True)
    out["price_daily"] = good.height
    out["price_daily:quarantined"] = bad.height
    if run is not None:
        run.count("core.price_daily", in_=price.height, out=good.height, quarantined=bad.height)
        run.count("core.instrument", in_=instrument.height, out=out["instrument"])
    return out
