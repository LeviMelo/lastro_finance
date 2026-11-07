"""Tesouro Direto bonds and their daily prices (PLAN §4.3.4 `tesouro_price_daily`).

- `core/tesouro_bond`: one row per (title, maturity): `instrument_id` = `T` + 12 hex of sha256("<title>|<maturity>"),
  the indexer and whether it pays semiannual coupons, read from the title name Tesouro uses.
- `core/tesouro_price_daily`: per bond and base date, the morning buy/sell rates and PUs. Staging keeps only rows that
  changed between daily files (ADR-0014); here each (bond, date) keeps every distinct value with `version` 1, 2… in
  the order the files were fetched, and `kt_first_seen_at` (PLAN invariant 3).
"""

from __future__ import annotations

import hashlib

import polars as pl

from fin.config import Zones
from fin.schema import Column, Contract
from fin.store.manifest import Manifest
from fin.store.runs import IngestRun
from fin.store.tables import read_parquet_dir, write_parquet

INDEXER = {  # title (as Tesouro writes it) -> (indexer, pays coupons)
    "Tesouro Prefixado": ("PRE", False),
    "Tesouro Prefixado com Juros Semestrais": ("PRE", True),
    "Tesouro IPCA+": ("IPCA", False),
    "Tesouro IPCA+ com Juros Semestrais": ("IPCA", True),
    "Tesouro Selic": ("SELIC", False),
    "Tesouro IGPM+ com Juros Semestrais": ("IGPM", True),
    "Tesouro Educa+": ("IPCA", False),
    "Tesouro Renda+ Aposentadoria Extra": ("IPCA", False),
}

BOND = Contract(
    table="core.tesouro_bond",
    version=1,
    description="A Tesouro Direto bond: one title and maturity.",
    provenance=False,
    columns=(
        Column("instrument_id", pl.String, "T + 12 hex of sha256(title|maturity)", "id do instrumento", nullable=False),
        Column("title", pl.String, "Tipo Titulo as written", "título", nullable=False),
        Column("maturity", pl.Date, "maturity", "vencimento", "date", nullable=False),
        Column("indexer", pl.String, "PRE, IPCA, SELIC, IGPM", "indexador", nullable=False),
        Column("coupons", pl.Boolean, "pays semiannual coupons", "juros semestrais", nullable=False),
        Column("first_date", pl.Date, "first base date in the file", "primeira data", "date", nullable=False),
        Column("last_date", pl.Date, "last base date in the file", "última data", "date", nullable=False),
    ),
    key=("instrument_id",),
)

PRICE = Contract(
    table="core.tesouro_price_daily",
    version=1,
    description="Tesouro Direto morning rates and unit prices per bond and base date, versioned.",
    columns=(
        Column("instrument_id", pl.String, "bond id", "id do instrumento", nullable=False),
        Column("base_date", pl.Date, "date of the quote", "data base", "date", nullable=False),
        Column("buy_rate", pl.Decimal(9, 4), "rate to buyers (Selic: spread)", "taxa de compra", "% a.a."),
        Column("sell_rate", pl.Decimal(9, 4), "rate to sellers", "taxa de venda", "% a.a."),
        Column("buy_pu", pl.Decimal(18, 6), "unit price to buy; null when not offered", "PU de compra", "BRL per bond"),
        Column(
            "sell_pu", pl.Decimal(18, 6), "unit price to sell; null when not offered", "PU de venda", "BRL per bond"
        ),
        Column("base_pu", pl.Decimal(18, 6), "reference unit price", "PU base", "BRL per bond", nullable=False),
        Column("version", pl.Int32, "1 for the first value seen; +1 at each change", "versão", "count", nullable=False),
        Column(
            "kt_first_seen_at",
            pl.Datetime("us", "UTC"),
            "first fetch of a file with this value",
            "visto em",
            "timestamp",
            nullable=False,
        ),
    ),
    key=("instrument_id", "base_date", "version"),
)


def bond_id(title: str, maturity: str) -> str:
    return "T" + hashlib.sha256(f"{title}|{maturity}".encode()).hexdigest()[:12]


def build(zones: Zones, run: IngestRun | None = None) -> dict[str, int]:
    s = read_parquet_dir(zones.staging / "tesouro_transparente" / "price_rate")
    if s is None or not s.height:
        return {}
    fetched = (
        Manifest(zones.manifest)
        .read()
        .filter(pl.col("source_id") == "tesouro_transparente")
        .group_by("raw_sha256")
        .agg(pl.col("fetched_at").min().alias("kt_first_seen_at"))
    )
    s = s.join(fetched, on="raw_sha256", how="left").with_columns(
        pl.struct("title", pl.col("maturity").cast(pl.String))
        .map_elements(lambda r: bond_id(r["title"], r["maturity"]), return_dtype=pl.String)
        .alias("instrument_id")
    )
    value = ["buy_rate", "sell_rate", "buy_pu", "sell_pu", "base_pu"]
    s = s.sort("instrument_id", "base_date", "kt_first_seen_at")
    changed = pl.any_horizontal(
        [pl.col(c).ne_missing(pl.col(c).shift(1).over("instrument_id", "base_date")) for c in value]
    )
    first = pl.col("kt_first_seen_at").shift(1).over("instrument_id", "base_date").is_null()
    v = s.filter(first | changed).with_columns(
        pl.int_range(1, pl.len() + 1, dtype=pl.Int32).over("instrument_id", "base_date").alias("version")
    )
    price = v.select(PRICE.names)
    bonds = (
        s.group_by("instrument_id", "title", "maturity")
        .agg(pl.col("base_date").min().alias("first_date"), pl.col("base_date").max().alias("last_date"))
        .with_columns(
            pl.col("title").replace_strict({k: v[0] for k, v in INDEXER.items()}, default="?").alias("indexer"),
            pl.col("title")
            .replace_strict({k: v[1] for k, v in INDEXER.items()}, default=False, return_dtype=pl.Boolean)
            .alias("coupons"),
        )
        .select(BOND.names)
        .sort("title", "maturity")
    )
    out: dict[str, int] = {}
    for name, contract, frame in (("tesouro_bond", BOND, bonds), ("tesouro_price_daily", PRICE, price)):
        good, bad = contract.split(frame)
        write_parquet(good, zones.core / name / f"{name}.parquet")
        out[name] = good.height
        out[f"{name}:quarantined"] = bad.height
        if run is not None:
            run.count(f"core.{name}", in_=frame.height, out=good.height, quarantined=bad.height)
    return out
