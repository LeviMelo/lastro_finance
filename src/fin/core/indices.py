"""Index membership through time (ADR-0036): B3's own portfolios where the daily bulletin has them (2022-03 →,
`b3_bdi_pdf`), and before that the monthly holdings of the ETF that tracks each index (Fundos.NET CDA, 2018 →).

Which ETF tracks which index is measured, not assumed. Over every month both exist, an ETF's equity tickers are
compared with each index's tickers on the last bulletin of the month; the index whose Jaccard similarity is highest
and at least `MATCH_MIN` in most compared months is the ETF's (`core.etf_index`). Before the bulletin's first date,
the membership of an index is the holdings of its best-matched ETF that month (`source` = `etf_cda`, a proxy:
an ETF can hold a few names outside its index or miss a few inside it).
"""

from __future__ import annotations

import polars as pl

from fin.config import Zones
from fin.store.tables import read_parquet_dir, write_parquet

MATCH_MIN = 0.90  # Jaccard of an ETF's equity tickers with an index's in a month, to count as tracking it
MATCH_SHARE = 0.80  # ...in at least this share of the months compared
# one index printed under two names: IBrX 100 is "IBXX" in most bulletins and "IBRX" in some (2022-09-01, 2026-09)
ALIASES = {"IBRX": "IBXX"}


def _official(zones: Zones) -> pl.DataFrame | None:
    comp = read_parquet_dir(zones.staging / "b3_bdi_pdf" / "index_composition")
    if comp is None or not comp.height:
        return None
    # the portfolio in force on a bulletin date: the one whose quadrimester holds it (a quadrimester's first session
    # also prints the incoming one)
    inforce = (pl.col("period_start") <= pl.col("bulletin_date")) & (pl.col("bulletin_date") <= pl.col("period_end"))
    return (
        comp.with_columns(pl.col("index_name").replace(ALIASES))
        .filter(inforce | pl.col("period_start").is_null())
        .unique(["bulletin_date", "index_name", "ticker"])
        .select("bulletin_date", "index_name", "ticker", "theoretical_qty", "weight_pct", "raw_sha256")
    )


def _etf_holdings(zones: Zones) -> pl.DataFrame | None:
    pos = read_parquet_dir(zones.staging / "b3_fundosnet_cda" / "position")
    if pos is None or not pos.height:
        return None
    ticker = pl.col("asset_code").str.strip_chars()
    return (
        pos.filter(ticker.str.contains(r"^[A-Z0-9]{4}\d{1,2}$") & (pl.col("final_qty") > 0))
        .select("fund_cnpj", "reference_month", ticker.alias("ticker"), "raw_sha256")
        .unique(["fund_cnpj", "reference_month", "ticker"])
    )


def etf_index(official: pl.DataFrame, holdings: pl.DataFrame) -> pl.DataFrame:
    """For each ETF, the index its holdings match (`MATCH_MIN` in `MATCH_SHARE` of the months compared)."""
    last = (
        official.with_columns(pl.col("bulletin_date").dt.truncate("1mo").alias("reference_month"))
        .filter(pl.col("bulletin_date") == pl.col("bulletin_date").max().over("reference_month"))
        .select("reference_month", "index_name", "ticker")
    )
    size_i = last.group_by("reference_month", "index_name").agg(pl.len().alias("n_i"))
    size_e = holdings.group_by("fund_cnpj", "reference_month").agg(pl.len().alias("n_e"))
    both = (
        holdings.select("fund_cnpj", "reference_month", "ticker")
        .join(last, on=["reference_month", "ticker"])
        .group_by("fund_cnpj", "reference_month", "index_name")
        .agg(pl.len().alias("n_both"))
        .join(size_i, on=["reference_month", "index_name"])
        .join(size_e, on=["fund_cnpj", "reference_month"])
        .with_columns((pl.col("n_both") / (pl.col("n_i") + pl.col("n_e") - pl.col("n_both"))).alias("jaccard"))
    )
    best = both.sort("jaccard", descending=True).unique(["fund_cnpj", "reference_month"], keep="first")
    months = best.group_by("fund_cnpj").agg(pl.len().alias("months_compared"))
    score = (
        best.filter(pl.col("jaccard") >= MATCH_MIN)
        .group_by("fund_cnpj", "index_name")
        .agg(pl.len().alias("months_matched"), pl.col("jaccard").median().alias("median_jaccard"),
             pl.col("reference_month").min().alias("first_month"), pl.col("reference_month").max().alias("last_month"))
        .join(months, on="fund_cnpj")
        .filter(pl.col("months_matched") >= MATCH_SHARE * pl.col("months_compared"))
    )  # fmt: skip
    return score.sort("index_name", "median_jaccard", descending=[False, True])


def membership(official: pl.DataFrame, holdings: pl.DataFrame, mapping: pl.DataFrame) -> pl.DataFrame:
    """Per index and month, its members: B3's (last bulletin of the month) from the bulletin's first month; before it,
    the holdings of the best-matched ETF reporting that month."""
    first = official["bulletin_date"].min()
    off = (
        official.with_columns(pl.col("bulletin_date").dt.truncate("1mo").alias("month"))
        .filter(pl.col("bulletin_date") == pl.col("bulletin_date").max().over("month", "index_name"))
        .select("month", "index_name", "ticker", "weight_pct", pl.lit("b3_bdi").alias("source"),
                pl.lit(None, dtype=pl.String).alias("fund_cnpj"), "raw_sha256")
    )  # fmt: skip
    # each month, the best-matched ETF that reported holdings that month (BOVA11 back to 2018, not a 2023 launch)
    proxy = (
        holdings.join(mapping.select("fund_cnpj", "index_name", "median_jaccard"), on="fund_cnpj")
        .filter(pl.col("reference_month") < pl.lit(first).dt.truncate("1mo"))
        .filter(pl.col("median_jaccard") == pl.col("median_jaccard").max().over("index_name", "reference_month"))
        .filter(pl.col("fund_cnpj") == pl.col("fund_cnpj").min().over("index_name", "reference_month"))
        .select(pl.col("reference_month").alias("month"), "index_name", "ticker",
                pl.lit(None, dtype=pl.Decimal(38, 6)).alias("weight_pct"), pl.lit("etf_cda").alias("source"),
                "fund_cnpj", "raw_sha256")
    )  # fmt: skip
    return pl.concat([off, proxy], how="vertical_relaxed").sort("index_name", "month", "ticker")


def build(zones: Zones) -> dict[str, int]:
    official, holdings = _official(zones), _etf_holdings(zones)
    if official is None or holdings is None:
        return {}
    mapping = etf_index(official, holdings)
    members = membership(official, holdings, mapping)
    write_parquet(mapping, zones.core / "etf_index" / "etf_index.parquet")
    write_parquet(members, zones.core / "index_member" / "index_member.parquet")
    return {"etf_index": mapping.height, "index_member": members.height}
