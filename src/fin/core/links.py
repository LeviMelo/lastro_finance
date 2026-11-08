"""Links between instruments (PLAN §4.3.3's event graph, first edges; ADR-0019).

`core/instrument_link`: one row per (from instrument, to instrument, date, kind):
- `ticker_continuity`: one ticker trades under ISIN A until a session and under ISIN B from the next (within 5
  sessions), A never again: the same line of shares under a new ISIN. `price_ratio` = close of A's last session /
  close of B's first.
- `name_continuity`: instrument A trades for the last time and a new instrument B, under another ticker, trades for
  the first time within 5 sessions, with the same NOMRES and the same share class (first word of ESPECI) on those two
  sessions, and no other candidate on either side: a renamed line of shares (ITAU4 -> ITUB4, 2009-05-20).
- B3 Supplement events whose issued asset is another ISIN: `BONIFICACAO` in another class, `CIS RED CAP` (spin-off
  with capital reduction), `INCORPORACAO`, `RESG TOTAL RV`, `REST CAP ACOES`. `factor` is B3's as written; its unit
  depends on the label and is not interpreted here.

Links carry no price adjustment yet: they connect histories so that a holding or a backtest can follow a share
across them.
"""

from __future__ import annotations

import polars as pl

from fin.config import Zones
from fin.schema import Column, Contract
from fin.store.runs import IngestRun
from fin.store.tables import read_parquet_dir, write_parquet

LINK = Contract(
    table="core.instrument_link",
    version=1,
    description="An edge from one instrument to another: same shares under a new ISIN, or shares issued by an event.",
    provenance=False,
    columns=(
        Column("from_instrument_id", pl.String, "instrument before", "de", nullable=False),
        Column("to_instrument_id", pl.String, "instrument after, or issued", "para", nullable=False),
        Column(
            "link_date",
            pl.Date,
            "first session of the new ISIN, or the data-com of the event",
            "data",
            "date",
            nullable=False,
        ),
        Column(
            "kind",
            pl.String,
            "ticker_continuity, name_continuity, or the B3 label (CIS RED CAP, INCORPORACAO...)",
            "tipo",
            nullable=False,
        ),
        Column("ticker", pl.String, "the ticker kept (ticker_continuity) or the new one (name_continuity)", "código"),
        Column("factor", pl.Decimal(38, 18), "B3 factor as written (label-dependent unit)", "fator", "label-dependent"),
        Column("price_ratio", pl.Float64, "close before / close after (ticker_continuity)", "razão de preços", "ratio"),
        Column("source_id", pl.String, "b3_cotahist or b3_company_events", "fonte", nullable=False),
    ),
    key=("from_instrument_id", "to_instrument_id", "link_date", "kind"),
)


def _spans(zones: Zones) -> pl.DataFrame:
    """Per (ticker, instrument): first and last session index, their closes and dates; `last_k` of the instrument."""
    pd = (
        pl.scan_parquet(zones.core / "price_daily" / "*.parquet")
        .filter(pl.col("market_segment") == "lote_padrao")
        .select("instrument_id", "ticker", "trade_date", pl.col("close").cast(pl.Float64))
        .collect()
    )
    sess = pd.select("trade_date").unique().sort("trade_date").with_row_index("k")
    pd = pd.join(sess, on="trade_date")
    span = pd.group_by("ticker", "instrument_id").agg(
        pl.col("k").min().alias("k0"),
        pl.col("k").max().alias("k1"),
        pl.col("close").sort_by("k").first().alias("c0"),
        pl.col("close").sort_by("k").last().alias("c1"),
        pl.col("trade_date").min().alias("d0"),
        pl.col("trade_date").max().alias("d1"),
    )
    ends = pd.group_by("instrument_id").agg(pl.col("k").min().alias("first_k"), pl.col("k").max().alias("last_k"))
    return span.join(ends, on="instrument_id")


def ticker_continuity(zones: Zones) -> pl.DataFrame:
    span = _spans(zones)
    a = span.filter(pl.col("k1") == pl.col("last_k"))  # A never trades again
    j = a.join(span, on="ticker", suffix="_b").filter(
        (pl.col("instrument_id") != pl.col("instrument_id_b"))
        & (pl.col("k0_b") > pl.col("k1"))
        & (pl.col("k0_b") - pl.col("k1") <= 5)
    )
    return j.select(
        pl.col("instrument_id").alias("from_instrument_id"),
        pl.col("instrument_id_b").alias("to_instrument_id"),
        pl.col("d0_b").alias("link_date"),
        pl.lit("ticker_continuity").alias("kind"),
        "ticker",
        pl.lit(None, dtype=pl.Decimal(38, 18)).alias("factor"),
        (pl.col("c1") / pl.col("c0_b")).alias("price_ratio"),
        pl.lit("b3_cotahist").alias("source_id"),
    )


def _names(zones: Zones) -> pl.DataFrame | None:
    """NOMRES and share class per (ticker, standard-lot session), from COTAHIST staging."""
    root = zones.staging / "b3_cotahist" / "quote"
    if not root.exists():
        return None
    q = pl.scan_parquet(root / "**" / "*.parquet", hive_partitioning=False).filter(pl.col("tpmerc") == 10)
    return (
        q.select(
            "ticker",
            "trade_date",
            pl.col("short_name").str.strip_chars().alias("name"),
            pl.col("especi").str.strip_chars().str.split(" ").list.first().alias("cls"),
        )
        .unique(["ticker", "trade_date"])
        .collect()
    )


def name_continuity(zones: Zones) -> pl.DataFrame:
    names = _names(zones)
    if names is None:
        return pl.DataFrame(schema=LINK.schema())
    span = _spans(zones)
    a = span.filter(pl.col("k1") == pl.col("last_k")).join(
        names, left_on=["ticker", "d1"], right_on=["ticker", "trade_date"]
    )
    b = span.filter(pl.col("k0") == pl.col("first_k")).join(
        names, left_on=["ticker", "d0"], right_on=["ticker", "trade_date"]
    )
    j = a.join(b, on=["name", "cls"], suffix="_b").filter(
        (pl.col("instrument_id") != pl.col("instrument_id_b"))
        & (pl.col("ticker") != pl.col("ticker_b"))
        & (pl.col("k0_b") > pl.col("k1"))
        & (pl.col("k0_b") - pl.col("k1") <= 5)
    )
    # subscription rights are never the same line of shares as anything (AMER1 -> AMER95, TMAR1 -> TMAR11)
    ip = zones.core / "instrument" / "instrument.parquet"
    if ip.exists():
        rights = pl.read_parquet(ip).filter(pl.col("asset_class") == "right")["instrument_id"].to_list()
        j = j.filter(~pl.col("instrument_id").is_in(rights) & ~pl.col("instrument_id_b").is_in(rights))
    # one to one only: a name shared by several lines that end or start together is not evidence
    j = j.filter((pl.len().over("instrument_id") == 1) & (pl.len().over("instrument_id_b") == 1))
    return j.select(
        pl.col("instrument_id").alias("from_instrument_id"),
        pl.col("instrument_id_b").alias("to_instrument_id"),
        pl.col("d0_b").alias("link_date"),
        pl.lit("name_continuity").alias("kind"),
        pl.col("ticker_b").alias("ticker"),
        pl.lit(None, dtype=pl.Decimal(38, 18)).alias("factor"),
        (pl.col("c1") / pl.col("c0_b")).alias("price_ratio"),
        pl.lit("b3_cotahist").alias("source_id"),
    )


def b3_links(zones: Zones) -> pl.DataFrame:
    s = read_parquet_dir(zones.staging / "b3_company_events" / "stock_event")
    if s is None or not s.height:
        return pl.DataFrame(schema=LINK.schema())
    ids = pl.read_parquet(zones.core / "instrument_identifier" / "instrument_identifier.parquet").filter(
        pl.col("scheme") == "ISIN"
    )
    isin = ids.select("instrument_id", pl.col("value").alias("isin")).unique("isin")
    s = s.unique(["isin", "asset_issued", "label", "factor", "last_date_prior"]).filter(
        pl.col("asset_issued").is_not_null()
        & (pl.col("asset_issued") != "")
        & (pl.col("asset_issued") != pl.col("isin"))
        & pl.col("last_date_prior").is_not_null()
    )
    s = s.join(isin.rename({"instrument_id": "from_instrument_id"}), on="isin").join(
        isin.rename({"instrument_id": "to_instrument_id", "isin": "asset_issued"}), on="asset_issued"
    )
    return s.select(
        "from_instrument_id",
        "to_instrument_id",
        pl.col("last_date_prior").alias("link_date"),
        pl.col("label").alias("kind"),
        pl.lit(None, dtype=pl.String).alias("ticker"),
        "factor",
        pl.lit(None, dtype=pl.Float64).alias("price_ratio"),
        pl.lit("b3_company_events").alias("source_id"),
    )


def build(zones: Zones, run: IngestRun | None = None) -> dict[str, int]:
    if not (zones.core / "price_daily").exists():
        return {}
    tc = ticker_continuity(zones)
    nc = name_continuity(zones).join(tc, on=["from_instrument_id", "to_instrument_id"], how="anti")
    links = pl.concat([tc, nc, b3_links(zones)], how="vertical_relaxed").unique(
        ["from_instrument_id", "to_instrument_id", "link_date", "kind"]
    )
    good, bad = LINK.split(links.select(LINK.names))
    write_parquet(good.sort("link_date"), zones.core / "instrument_link" / "instrument_link.parquet")
    if run is not None:
        run.count("core.instrument_link", in_=links.height, out=good.height, quarantined=bad.height)
    return {"instrument_link": good.height, "instrument_link:quarantined": bad.height}
