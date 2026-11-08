"""ETF NAV and the ETF <-> quota link, built once into core (ADR-0029).

`core.etf_nav`: every daily report of an ETF with its knowledge time.
- Fundos.NET (2018-): every delivered version, `delivered_at` from its listing row.
- Before that, CVM's INF_DIARIO rows of FIIM funds (2004-2018). The CVM register keeps cancelled funds, so dead
  ETFs are included.
- `is_latest` marks, per fund and date, Fundos.NET's latest delivered version, else CVM's row.

`core.etf_link`: fund CNPJ -> ETF quota instrument, by two routes:
- `trading_name`: the Fundos.NET listing's B3 trading name equals COTAHIST's NOMRES (CODBDI 14).
- `b3_listing`: B3's listed-funds page lists the fund under an acronym and gives its report ids; the report names
  the CNPJ (`b3_funds_listed`), and the quota is the ticker acronym + "11".
A link is `verified` when the median close / NAV over common days is within ETF_LINK_TOLERANCE of 1.

These were catalog views until 2026-11-08: each query re-scanned CVM's 82 M daily rows and joined them to prices,
and two queries spilled 38 GB and 35 GB of DuckDB temp files. Built here with lazy scans whose filters push down,
the inputs are read once.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from fin.config import Zones
from fin.schema import Column, Contract
from fin.store.runs import IngestRun
from fin.store.tables import write_parquet

ETF_LINK_TOLERANCE = 0.10  # crypto and foreign ETFs sit 2-5 % off their NAV; a wrong ticker is off by far more
QUOTA = pl.Decimal(38, 12)
MONEY = pl.Decimal(38, 4)

ETF_NAV = Contract(
    table="core.etf_nav",
    version=1,
    description="An ETF's daily report (NAV per quota, net assets, flows) with its knowledge time and source.",
    columns=(
        Column("fund_cnpj", pl.String, "fund (class) CNPJ, 14 digits", "CNPJ", nullable=False),
        Column("reference_date", pl.Date, "NAV date", "data de competência", "date", nullable=False),
        Column("source", pl.String, "fundosnet or cvm_inf_diario", "fonte", nullable=False),
        Column("doc_id", pl.Int64, "Fundos.NET document id (null for CVM rows)", "id do documento"),
        Column("delivered_at", pl.Datetime("us", "UTC"), "delivery minute (Fundos.NET)", "entrega", "timestamp"),
        Column("version", pl.Int32, "Fundos.NET filing version", "versão"),
        Column("trading_name", pl.String, "B3 trading name in the listing", "nome de pregão"),
        Column("quota_value_brl", QUOTA, "NAV per quota", "valor da cota", "BRL per quota"),
        Column("net_assets_brl", MONEY, "net assets", "patrimônio líquido", "BRL"),
        Column("portfolio_value_brl", MONEY, "portfolio value", "valor da carteira", "BRL"),
        Column("subscriptions_brl", MONEY, "subscriptions of the day", "captação", "BRL"),
        Column("redemptions_brl", MONEY, "redemptions of the day", "resgate", "BRL"),
        Column("holders", pl.Int64, "number of holders", "cotistas", "count"),
        Column("is_latest", pl.Boolean, "the row that holds for this fund and date", "vigente", nullable=False),
    ),
    key=("fund_cnpj", "reference_date", "source", "doc_id"),
)
ETF_LINK = Contract(
    table="core.etf_link",
    version=1,
    description="An ETF fund (CNPJ) and its quota instrument, with how it was matched and the price check.",
    provenance=False,
    columns=(
        Column("fund_cnpj", pl.String, "fund CNPJ", "CNPJ", nullable=False),
        Column("instrument_id", pl.String, "the quota instrument", "id do instrumento", nullable=False),
        Column("isin", pl.String, "the quota's ISIN", "ISIN"),
        Column("trading_name", pl.String, "B3 trading name", "nome de pregão"),
        Column("methods", pl.String, "trading_name, b3_listing or both (comma-separated)", "métodos", nullable=False),
        Column("first_date", pl.Date, "first NAV date of the fund", "primeira data", "date"),
        Column("last_date", pl.Date, "last NAV date of the fund", "última data", "date"),
        Column("common_days", pl.Int64, "days with both a close and a NAV", "dias em comum", "count"),
        Column("median_ratio", pl.Float64, "median close / NAV per quota", "mediana preço/cota", "ratio"),
        Column("verified", pl.Boolean, "median within the tolerance of 1", "verificado", nullable=False),
    ),
    key=("fund_cnpj", "instrument_id"),
)
CONTRACTS = {"etf_nav": ETF_NAV, "etf_link": ETF_LINK}


def _scan(path: Path) -> pl.LazyFrame | None:
    files = list(path.glob("**/*.parquet")) if path.exists() else []
    if not files:
        return None
    return pl.scan_parquet(files, hive_partitioning=False, missing_columns="insert", extra_columns="ignore")


def _digits(col: str) -> pl.Expr:
    return pl.col(col).str.replace_all(r"\D", "")


def nav_frame(zones: Zones) -> pl.DataFrame | None:
    s = zones.staging
    daily, listing = _scan(s / "b3_fundosnet_daily" / "daily"), _scan(s / "b3_fundosnet_daily" / "listing")
    if daily is None or listing is None:
        return None
    lst = listing.group_by("doc_id").agg(
        pl.col("delivered_at").min(), pl.col("version").max(), pl.col("trading_name").drop_nulls().first()
    )
    fnet = (
        daily.join(lst, on="doc_id", how="left")
        .with_columns(pl.lit("fundosnet").alias("source"))
        .unique(["doc_id", "fund_cnpj", "reference_date"])  # staging may repeat a document (dedup by content)
        .collect()
    )
    cnpjs = set(fnet["fund_cnpj"].unique().to_list())
    for sub, col, cond in (
        ("fund", "cnpj", pl.col("fund_type") == "FIIM"),
        ("registered_class", "cnpj", pl.col("class_type").str.ends_with("FIIM")),
    ):
        reg = _scan(s / "cvm_fi_cadastro" / sub)
        if reg is not None:
            cnpjs |= set(reg.filter(cond).select(_digits(col).alias("c")).collect()["c"].to_list())
    formatted = [f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}" for c in cnpjs if len(c) == 14]
    cvm_scan = _scan(s / "cvm_fi_inf_diario" / "daily")
    parts = [fnet]
    if cvm_scan is not None:  # INF_DIARIO writes the CNPJ formatted: the filter pushes down to the scan
        cvm = (
            cvm_scan.filter(pl.col("cnpj").is_in(formatted))
            .select(
                _digits("cnpj").alias("fund_cnpj"),
                "reference_date",
                "quota_value_brl",
                "net_assets_brl",
                "portfolio_value_brl",
                "subscriptions_brl",
                "redemptions_brl",
                "holders",
                "raw_sha256",
                "raw_locator",
                "ingest_run_id",
                pl.lit("cvm_inf_diario").alias("source"),
            )
            .collect()
        )
        parts.append(cvm)
    nav = pl.concat(parts, how="diagonal_relaxed")
    rank = (
        pl.col("source") == "fundosnet",
        pl.col("delivered_at").fill_null(pl.datetime(1900, 1, 1, time_zone="UTC")),
        pl.col("doc_id").fill_null(-1),
    )
    nav = nav.sort(["fund_cnpj", "reference_date", *rank], descending=[False, False, True, True, True])
    nav = nav.with_columns((pl.int_range(pl.len()).over("fund_cnpj", "reference_date") == 0).alias("is_latest"))
    cols = [c.name for c in ETF_NAV.columns] + ["raw_sha256", "raw_locator", "ingest_run_id"]
    return nav.select([pl.col(c).cast(t) if (t := _dtype(c)) is not None else pl.col(c) for c in cols])


def _dtype(name: str) -> pl.DataType | None:
    for c in ETF_NAV.columns:
        if c.name == name:
            return c.dtype  # type: ignore[return-value]
    return None


def link_frame(zones: Zones, nav: pl.DataFrame) -> pl.DataFrame:
    latest = nav.filter(pl.col("is_latest") & (pl.col("quota_value_brl") > 0))
    span = latest.group_by("fund_cnpj").agg(
        pl.col("reference_date").min().alias("first_date"), pl.col("reference_date").max().alias("last_date")
    )
    inst = pl.read_parquet(zones.core / "instrument" / "instrument.parquet")
    ids = pl.read_parquet(zones.core / "instrument_identifier" / "instrument_identifier.parquet")
    isin = ids.filter(pl.col("scheme") == "ISIN").group_by("instrument_id").agg(pl.col("value").first().alias("isin"))
    names = latest.drop_nulls("trading_name").select("fund_cnpj", "trading_name").unique()
    by_name = names.join(
        inst.filter(pl.col("codbdi") == "14").select("instrument_id", pl.col("short_name").alias("trading_name")),
        on="trading_name",
    ).with_columns(pl.lit("trading_name").alias("method"))
    pairs = [by_name.select("fund_cnpj", "instrument_id", "method")]
    lf, fr = (
        _scan(zones.staging / "b3_funds_listed" / "listed_fund"),
        _scan(zones.staging / "b3_funds_listed" / "fund_report"),
    )
    if lf is not None and fr is not None:
        acr = (
            lf.filter(pl.col("type_fund").str.starts_with("ETF")).select("fnet_id", "acronym").unique()
            .join(fr.select("fnet_id", "doc_id").unique(), on="fnet_id").collect()
            .join(nav.filter(pl.col("doc_id").is_not_null()).select("doc_id", "fund_cnpj"), on="doc_id")
            .select("fund_cnpj", (pl.col("acronym") + "11").alias("value")).unique()
        )  # fmt: skip
        tick = ids.filter(pl.col("scheme") == "TICKER").select("instrument_id", "value").unique()
        pairs.append(
            acr.join(tick, on="value").select("fund_cnpj", "instrument_id", pl.lit("b3_listing").alias("method"))
        )
    p = (
        pl.concat(pairs)
        .group_by("fund_cnpj", "instrument_id")
        .agg(pl.col("method").unique().sort().str.join(",").alias("methods"))
    )
    if not p.height:
        return pl.DataFrame(schema={c.name: c.dtype for c in ETF_LINK.columns})
    wanted = p["instrument_id"].unique().implode()
    prices = (
        pl.scan_parquet(zones.core / "price_daily" / "*.parquet")
        .filter(pl.col("instrument_id").is_in(wanted) & (pl.col("market_segment") == "lote_padrao"))
        .select("instrument_id", pl.col("trade_date").alias("reference_date"), "close")
        .collect()
    )
    ratio = (
        p.join(prices, on="instrument_id")
        .join(latest.select("fund_cnpj", "reference_date", "quota_value_brl"), on=["fund_cnpj", "reference_date"])
        .group_by("fund_cnpj", "instrument_id")
        .agg(
            pl.len().alias("common_days"),
            (pl.col("close").cast(pl.Float64) / pl.col("quota_value_brl").cast(pl.Float64))
            .median()
            .alias("median_ratio"),
        )
    )
    return (
        p.join(ratio, on=["fund_cnpj", "instrument_id"], how="left")
        .join(span, on="fund_cnpj", how="left")
        .join(isin, on="instrument_id", how="left")
        .join(names.group_by("fund_cnpj").agg(pl.col("trading_name").first()), on="fund_cnpj", how="left")
        .with_columns(
            pl.col("common_days").cast(pl.Int64),
            ((pl.col("median_ratio") - 1).abs() <= ETF_LINK_TOLERANCE).fill_null(False).alias("verified"),
        )
        .select(ETF_LINK.names)
    )


def build(zones: Zones, run: IngestRun | None = None) -> dict[str, int]:
    nav = nav_frame(zones)
    if nav is None:
        return {}
    good, bad = ETF_NAV.split(nav)
    write_parquet(good, zones.core / "etf_nav" / "etf_nav.parquet")
    out = {"etf_nav": good.height, "etf_nav:quarantined": bad.height}
    if (zones.core / "instrument" / "instrument.parquet").exists():
        link = link_frame(zones, good)
        lg, lb = ETF_LINK.split(link)
        write_parquet(lg, zones.core / "etf_link" / "etf_link.parquet")
        out |= {"etf_link": lg.height, "etf_link:quarantined": lb.height}
    if run is not None:
        run.count("core.etf_nav", in_=nav.height, out=good.height, quarantined=bad.height)
    return out
