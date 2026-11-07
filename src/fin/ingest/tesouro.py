"""Tesouro Direto prices and rates (`PrecoTaxaTesouroDireto.csv`) -> staging `price_rate`
(docs/sources/tesouro_transparente.md).

Source-shaped: one row per (title as written, maturity, base date), exact decimals. The file is the whole history
re-uploaded every morning, so each archived file is a full snapshot; a later core step keeps one version per change
(PLAN §4.3.4 `tesouro_price_daily`), once Tesouro titles have instrument ids.

A zero buy or sell PU (`0,00`, mostly on a title's last days) means that side was not offered: it is read as null.
A zero base PU is not a price: that row is quarantined. A zero buy rate is genuine for Tesouro Selic (a spread over
Selic that rounds to 0).
"""

from __future__ import annotations

import io
from collections.abc import Iterable
from typing import Any

import polars as pl

from fin.ingest.base import Parsed
from fin.schema import Column, Contract, Rule

HEADER = (
    "Tipo Titulo",
    "Data Vencimento",
    "Data Base",
    "Taxa Compra Manha",
    "Taxa Venda Manha",
    "PU Compra Manha",
    "PU Venda Manha",
    "PU Base Manha",
)
RATE = pl.Decimal(9, 4)
PU = pl.Decimal(18, 6)
TITLES = (
    "Tesouro Prefixado",
    "Tesouro Prefixado com Juros Semestrais",
    "Tesouro IPCA+",
    "Tesouro IPCA+ com Juros Semestrais",
    "Tesouro Selic",
    "Tesouro IGPM+ com Juros Semestrais",
    "Tesouro Educa+",
    "Tesouro Renda+ Aposentadoria Extra",
)


class LayoutError(ValueError):
    pass


PRICE_RATE = Contract(
    table="staging.tesouro_transparente.price_rate",
    version=1,
    description="Tesouro Direto's morning buy/sell rates and unit prices, per title, maturity and base date.",
    columns=(
        Column("title", pl.String, "title name as written (Tipo Titulo)", "tipo de título", nullable=False),
        Column("maturity", pl.Date, "maturity date (Data Vencimento)", "data de vencimento", "date", nullable=False),
        Column("base_date", pl.Date, "date of the quote (Data Base)", "data base", "date", nullable=False),
        Column(
            "buy_rate",
            RATE,
            "rate offered to buyers; for Tesouro Selic the spread over Selic",
            "taxa de compra (manhã)",
            "% a.a.",
            nullable=False,
        ),
        Column("sell_rate", RATE, "rate offered to sellers", "taxa de venda (manhã)", "% a.a.", nullable=False),
        Column(
            "buy_pu",
            PU,
            "unit price to buy; null where the source writes 0,00 (not offered)",
            "PU de compra (manhã)",
            "BRL per bond",
        ),
        Column(
            "sell_pu",
            PU,
            "unit price to sell; null where the source writes 0,00 (not offered)",
            "PU de venda (manhã)",
            "BRL per bond",
        ),
        Column("base_pu", PU, "reference unit price (PU Base)", "PU base (manhã)", "BRL per bond", nullable=False),
    ),
    rules=(
        Rule("title_known", pl.col("title").is_in(TITLES)),
        Rule("base_pu_positive", pl.col("base_pu") > 0),
        Rule("maturity_after_base", pl.col("maturity") > pl.col("base_date")),
    ),
    key=("title", "maturity", "base_date"),
)


def parse_price_rate(blob: bytes, row: dict[str, Any]) -> pl.DataFrame:
    text = blob.decode("ascii")  # measured: ASCII only (docs/sources/tesouro_transparente.md §4)
    first = text.split("\n", 1)[0].rstrip("\r")
    if tuple(first.split(";")) != HEADER:
        raise LayoutError(f"Tesouro preço/taxa: header changed: {first!r}")
    df = pl.read_csv(io.StringIO(text), separator=";", infer_schema=False, has_header=True)
    if df.width != len(HEADER):
        raise LayoutError(f"Tesouro preço/taxa: {df.width} columns")
    for col, dtype in zip(HEADER[3:], (RATE, RATE, PU, PU, PU), strict=True):
        finest = df[col].str.split(",").list.get(1, null_on_oob=True).str.len_chars().max()
        if finest is not None and int(finest) > dtype.scale:  # type: ignore[arg-type]
            raise LayoutError(f"Tesouro preço/taxa: {col} has {finest} decimals; a cast would round")

    def dec(col: str, dtype: pl.DataType) -> pl.Expr:
        return pl.col(col).str.replace(",", ".", literal=True).cast(dtype)

    def pu_offered(col: str) -> pl.Expr:
        return pl.when(pl.col(col) != "0,00").then(dec(col, PU))

    def day(col: str) -> pl.Expr:
        return pl.col(col).str.strptime(pl.Date, "%d/%m/%Y")

    out = df.with_row_index("i", offset=2).select(
        pl.col("Tipo Titulo").alias("title"),
        day("Data Vencimento").alias("maturity"),
        day("Data Base").alias("base_date"),
        dec("Taxa Compra Manha", RATE).alias("buy_rate"),
        dec("Taxa Venda Manha", RATE).alias("sell_rate"),
        pu_offered("PU Compra Manha").alias("buy_pu"),
        pu_offered("PU Venda Manha").alias("sell_pu"),
        dec("PU Base Manha", PU).alias("base_pu"),
        pl.lit(row["raw_sha256"]).alias("raw_sha256"),
        ("line=" + pl.col("i").cast(pl.String)).alias("raw_locator"),
        pl.lit(row["ingest_run_id"]).alias("ingest_run_id"),
    )
    return out


def parse_payload(blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
    yield Parsed("price_rate", "all", parse_price_rate(blob, row))
