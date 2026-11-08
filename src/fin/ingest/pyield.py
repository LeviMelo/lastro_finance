"""pyield-data mirror (tier S: docs/sources/pyield_data.md) -> staging `bond_rate`, `future_daily`, `vna_ntnb`.

The mirror's files are Parquet with float columns. Floats are rounded to the precision the primary publishes and
then typed as Decimal: ANBIMA unit prices to 6 decimals, ANBIMA rates (fractions in the mirror) to 8 decimals (6 in
percent: ANBIMA publishes 4); B3 futures prices and rates to 6 decimals; VNA to 6 decimals (Tesouro publishes 6).
The rounding is stated here because it is a conversion, not a measurement.
"""

from __future__ import annotations

import io
from collections.abc import Iterable
from typing import Any

import polars as pl

from fin.ingest.base import Parsed
from fin.schema import Column, Contract

D6, D8 = pl.Decimal(24, 6), pl.Decimal(24, 8)


class LayoutError(ValueError):
    pass


BOND_RATE = Contract(
    table="staging.pyield_data.bond_rate",
    version=1,
    description="ANBIMA government-bond indicative rates and unit prices, as the pyield mirror serves them (2020-).",
    columns=(
        Column("reference_date", pl.Date, "data_referencia", "data", "date", nullable=False),
        Column("bond_type", pl.String, "titulo (LTN, NTN-F, NTN-B, LFT...)", "título", nullable=False),
        Column("selic_code", pl.Int64, "codigo_selic", "código Selic"),
        Column("base_date", pl.Date, "data_base", "data-base", "date"),
        Column("maturity", pl.Date, "data_vencimento", "vencimento", "date", nullable=False),
        Column("pu_brl", D6, "pu, rounded to 6 decimals", "PU", "BRL"),
        Column("bid_rate_pct", D6, "taxa_compra x 100, 6 decimals", "taxa de compra", "% a.a."),
        Column("ask_rate_pct", D6, "taxa_venda x 100, 6 decimals", "taxa de venda", "% a.a."),
        Column("indicative_rate_pct", D6, "taxa_indicativa x 100, 6 decimals", "taxa indicativa", "% a.a."),
    ),
)
FUTURE_DAILY = Contract(
    table="staging.pyield_data.future_daily",
    version=1,
    description="B3 futures daily summary (DI1, DAP, DDI, FRC, FRO, DOL, WDO, IND, WIN) per the mirror (2018-).",
    columns=(
        Column("trade_date", pl.Date, "TradDt", "pregão", "date", nullable=False),
        Column("ticker", pl.String, "TckrSymb", "código", nullable=False),
        Column("open_interest", pl.Int64, "OpnIntrst", "contratos em aberto", "contracts"),
        Column("trades", pl.Int64, "TradQty", "negócios", "count"),
        Column("contracts", pl.Int64, "FinInstrmQty", "contratos negociados", "contracts"),
        Column("notional_brl", pl.Decimal(24, 2), "NtlFinVol, 2 decimals", "volume financeiro", "BRL"),
        Column("best_bid", D6, "BestBidPric", "melhor compra", "contract quote"),
        Column("best_ask", D6, "BestAskPric", "melhor venda", "contract quote"),
        Column("open", D6, "FrstPric", "abertura", "contract quote"),
        Column("low", D6, "MinPric", "mínimo", "contract quote"),
        Column("high", D6, "MaxPric", "máximo", "contract quote"),
        Column("avg", D6, "TradAvrgPric", "médio", "contract quote"),
        Column("last", D6, "LastPric", "último", "contract quote"),
        Column("settlement", D6, "AdjstdQt: settlement price (PU for rate contracts)", "ajuste", "contract quote"),
        Column("settlement_rate", D6, "AdjstdQtTax: settlement rate (rate contracts)", "taxa de ajuste", "% a.a."),
        Column("max_limit", D6, "MaxTradLmt", "limite máximo", "contract quote"),
        Column("min_limit", D6, "MinTradLmt", "limite mínimo", "contract quote"),
    ),
)
VNA_NTNB = Contract(
    table="staging.pyield_data.vna_ntnb",
    version=1,
    description="NTN-B VNA per business day as the mirror computes it (2004-), with the inflation projection used.",
    columns=(
        Column("reference_date", pl.Date, "reference_date", "data", "date", nullable=False),
        Column("inflation_pct", D6, "inflation (monthly IPCA, actual or projected)", "inflação", "% a.m."),
        Column("vna_business_days", D6, "vna_du: pro rata by business days", "VNA (du)", "BRL"),
        Column("vna_calendar_days", D6, "vna_dc: pro rata by calendar days", "VNA (dc)", "BRL"),
    ),
)
CONTRACTS = {"bond_rate": BOND_RATE, "future_daily": FUTURE_DAILY, "vna_ntnb": VNA_NTNB}

BOND_COLS = ("data_referencia", "titulo", "codigo_selic", "data_base", "data_vencimento", "pu", "taxa_compra",
             "taxa_venda", "taxa_indicativa")  # fmt: skip
FUT = {"TradDt": "trade_date", "TckrSymb": "ticker", "OpnIntrst": "open_interest", "TradQty": "trades",
       "FinInstrmQty": "contracts", "NtlFinVol": "notional_brl", "BestBidPric": "best_bid",
       "BestAskPric": "best_ask", "FrstPric": "open", "MinPric": "low", "MaxPric": "high", "TradAvrgPric": "avg",
       "LastPric": "last", "AdjstdQt": "settlement", "AdjstdQtTax": "settlement_rate", "MaxTradLmt": "max_limit",
       "MinTradLmt": "min_limit"}  # fmt: skip
VNA = ("reference_date", "inflation", "vna_du", "vna_dc")


def _dec(col: str, scale: int, mult: float = 1.0) -> pl.Expr:
    return (pl.col(col) * mult).round(scale).cast(pl.Decimal(24, scale))


def _need(df: pl.DataFrame, cols: Iterable[str], name: str) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise LayoutError(f"pyield {name}: columns missing: {missing}")


def _with_prov(df: pl.DataFrame, row: dict[str, Any]) -> pl.DataFrame:
    return (
        df.with_row_index("_i")
        .with_columns(
            pl.lit(row["raw_sha256"]).alias("raw_sha256"),
            (pl.lit("row=") + pl.col("_i").cast(pl.String)).alias("raw_locator"),
            pl.lit(row["ingest_run_id"]).alias("ingest_run_id"),
        )
        .drop("_i")
    )


def parse_payload(blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
    ds = str(row["dataset_id"])
    df = pl.read_parquet(io.BytesIO(blob))
    if ds == "anbima_tpf":
        _need(df, BOND_COLS, ds)
        out = df.select(
            pl.col("data_referencia").alias("reference_date"),
            pl.col("titulo").alias("bond_type"),
            pl.col("codigo_selic").cast(pl.Int64).alias("selic_code"),
            pl.col("data_base").alias("base_date"),
            pl.col("data_vencimento").alias("maturity"),
            _dec("pu", 6).alias("pu_brl"),
            _dec("taxa_compra", 6, 100).alias("bid_rate_pct"),
            _dec("taxa_venda", 6, 100).alias("ask_rate_pct"),
            _dec("taxa_indicativa", 6, 100).alias("indicative_rate_pct"),
        )
        for y, part in _with_prov(out, row).group_by(pl.col("reference_date").dt.year()):
            yield Parsed("bond_rate", f"year={y[0]}", part)
    elif ds == "b3_futures":
        _need(df, FUT, ds)
        ints = ("open_interest", "trades", "contracts")
        out = df.select(
            *[
                (pl.col(k).cast(pl.Int64) if v in ints else pl.col(k)).alias(v)
                if v in (*ints, "trade_date", "ticker")
                else (_dec(k, 2) if v == "notional_brl" else _dec(k, 6)).alias(v)
                for k, v in FUT.items()
            ]
        )
        for y, part in _with_prov(out, row).group_by(pl.col("trade_date").dt.year()):
            yield Parsed("future_daily", f"year={y[0]}", part)
    elif ds == "vna_ntnb":
        _need(df, VNA, ds)
        out = df.select(
            pl.col("reference_date").cast(pl.Date),
            _dec("inflation", 6).alias("inflation_pct"),
            _dec("vna_du", 6).alias("vna_business_days"),
            _dec("vna_dc", 6).alias("vna_calendar_days"),
        )
        yield Parsed("vna_ntnb", "all", _with_prov(out, row))
    else:
        raise LayoutError(f"pyield: unknown dataset {ds}")
