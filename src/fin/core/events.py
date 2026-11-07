"""Corporate events and price adjustment factors (PLAN §4.3.3, §4.7; ADR-0016).

`core/corporate_event` holds one row per event of one instrument:
- **stock events** from B3's Supplement (by ISIN; tier U) and Yahoo (by ticker on the date; tier U), merged on
  (instrument, ex-date); ratio = new shares per old share, exact;
- **cash events** from B3's cash history (by issuer root and share class) and Fundos.NET (FII notices, by ISIN);
  `cash_per_share` in BRL per one share.

Each stock event carries its evidence: which sources report it, and whether the unadjusted prices moved by the
stated ratio across the ex-date (`price_check`: the close of the last session with the right over the first session
without it, divided by the ratio). The status is
`confirmed` (two sources, or one source and the price check), `price_only` (one source, the price check agrees),
`candidate` otherwise. Only `confirmed` and `price_only` events enter the adjustment factors. The check is made on
the day's net ratio per source group (B3 may record one operation as two same-day events), and passes when the move
is closer to the ratio than to no event, within a factor of 2.

The ex-date is the first B3 session after the data-com, taken from the sessions in `price_daily` (B3's own calendar);
Yahoo dates are already ex-dates.

`derived/adjustment_factor` (rebuilt, never the truth, PLAN invariant 6): per instrument and ex-date, the factor that
multiplies prices **before** the ex-date: 1/ratio for stock events; (1 − cash / close of the data-com) for cash.
"""

from __future__ import annotations

import math
from fractions import Fraction
from typing import Any

import polars as pl

from fin.config import Zones
from fin.schema import Column, Contract, Rule
from fin.store.runs import IngestRun
from fin.store.tables import read_parquet_dir, write_parquet

CASH = pl.Decimal(38, 18)
SMALL_LOG = math.log(1.2)
SMALL_GAP = math.log(1.1)
KT = pl.Datetime("us", "UTC")

# B3 Supplement labels: how the factor reads (docs/sources/b3_company_events.md §3, golden_events.md)
B3_STOCK = {
    "BONIFICACAO": "BONUS",  # factor = percent of new shares: ratio = 1 + f/100
    "DESDOBRAMENTO": "SPLIT",  # factor = percent increase: ratio = 1 + f/100
    "GRUPAMENTO": "REVERSE_SPLIT",  # factor = new per old: ratio = f
}
B3_CASH = {"DIVIDENDO": "DIVIDEND", "JRS CAP PROPRIO": "JCP", "RENDIMENTO": "INCOME", "AMORTIZACAO": "AMORTIZATION"}
TYPES = ("DIVIDEND", "JCP", "INCOME", "AMORTIZATION", "OTHER_CASH", "BONUS", "SPLIT", "REVERSE_SPLIT", "RIGHTS")

EVENT = Contract(
    table="core.corporate_event",
    version=1,
    description="One corporate event of one instrument, with its sources and evidence (ADR-0016).",
    provenance=False,
    columns=(
        Column("event_id", pl.String, "instrument_id|type|ex_date|n", "id do evento", nullable=False),
        Column("instrument_id", pl.String, "surrogate id", "id do instrumento", nullable=False),
        Column(
            "event_type",
            pl.String,
            "DIVIDEND, JCP, INCOME, AMORTIZATION, OTHER_CASH, BONUS, SPLIT, REVERSE_SPLIT",
            "tipo",
            nullable=False,
        ),
        Column(
            "data_com", pl.Date, "last session with the right (null when only Yahoo reports it)", "data com", "date"
        ),
        Column("ex_date", pl.Date, "first session without the right", "data ex", "date", nullable=False),
        Column("ratio_num", pl.Int64, "stock events: new shares per ratio_den old", "razão (numerador)", "shares"),
        Column("ratio_den", pl.Int64, "see ratio_num", "razão (denominador)", "shares"),
        Column(
            "cash_per_share",
            CASH,
            "cash events: BRL per one share; RIGHTS: the subscription price",
            "valor por ação",
            "BRL per share",
        ),
        Column("approved_on", pl.Date, "approval date", "aprovação", "date"),
        Column("payment_date", pl.Date, "payment date, where known", "pagamento", "date"),
        Column(
            "kt_published_at",
            KT,
            "when the source published it (Fundos.NET: the minute B3 received the notice); null where unknown",
            "publicado em",
            "timestamp",
        ),
        Column("sources", pl.String, "sources reporting it, comma-separated", "fontes", nullable=False),
        Column(
            "price_check",
            pl.Float64,
            "stock events: (close before / close on ex) / ratio; 1 = exact",
            "teste de preço",
            "ratio",
        ),
        Column(
            "status",
            pl.String,
            "confirmed, price_only, candidate (stock events); reported (cash)",
            "situação",
            nullable=False,
        ),
    ),
    rules=(
        Rule("type_known", pl.col("event_type").is_in(TYPES)),
        Rule("ratio_positive", pl.col("ratio_num").is_null() | ((pl.col("ratio_num") > 0) & (pl.col("ratio_den") > 0))),
        Rule("cash_non_negative", pl.col("cash_per_share").is_null() | (pl.col("cash_per_share") >= 0)),
        Rule("ex_after_com", pl.col("data_com").is_null() | (pl.col("ex_date") > pl.col("data_com"))),
    ),
    key=("event_id",),
)

FACTOR = Contract(
    table="derived.adjustment_factor",
    version=1,
    description="Per instrument and ex-date: the factor multiplying prices before the ex-date (derived).",
    provenance=False,
    columns=(
        Column("instrument_id", pl.String, "surrogate id", "id do instrumento", nullable=False),
        Column("ex_date", pl.Date, "ex-date", "data ex", "date", nullable=False),
        Column(
            "split_factor",
            pl.Float64,
            "product of 1/ratio of the day's stock events",
            "fator de desdobramento",
            "ratio",
            nullable=False,
        ),
        Column(
            "cash_factor",
            pl.Float64,
            "product of (1 - cash/close of the data-com) of the day's cash events and of rights offerings' "
            "theoretical ex-rights factor",
            "fator de proventos",
            "ratio",
            nullable=False,
        ),
    ),
    key=("instrument_id", "ex_date"),
)


def _staging(zones: Zones, source: str, dataset: str) -> pl.DataFrame | None:
    return read_parquet_dir(zones.staging / source / dataset)


def sessions(zones: Zones) -> pl.Series:
    return (
        pl.scan_parquet(zones.core / "price_daily" / "*.parquet")
        .select("trade_date")
        .unique()
        .sort("trade_date")
        .collect()["trade_date"]
    )


def next_session(dates: pl.Series, after: pl.Series) -> pl.Series:
    """For each date in `after`, the first session strictly later."""
    idx = dates.search_sorted(after, side="right")
    return pl.Series([dates[int(i)] if int(i) < dates.len() else None for i in idx], dtype=pl.Date)


def b3_ratio(label: str, factor: Fraction) -> Fraction | None:
    kind = B3_STOCK.get(label)
    if kind in ("BONUS", "SPLIT"):
        return 1 + factor / 100
    if kind == "REVERSE_SPLIT":
        return factor
    return None


def _ids(zones: Zones) -> pl.DataFrame:
    return pl.read_parquet(zones.core / "instrument_identifier" / "instrument_identifier.parquet")


def stock_events(zones: Zones, dates: pl.Series) -> pl.DataFrame:
    ids = _ids(zones)
    isin = ids.filter(pl.col("scheme") == "ISIN").select("instrument_id", pl.col("value").alias("isin")).unique("isin")
    rows: list[dict[str, Any]] = []
    b3 = _staging(zones, "b3_company_events", "stock_event")
    if b3 is not None:
        b3 = b3.unique(["isin", "label", "factor", "last_date_prior"]).join(isin, on="isin", how="inner")
        # only events paid in the same class adjust its price; a bonus in another class (CYRE 2025-12: PN to ON
        # holders), a spin-off or an incorporation is a link between instruments (core/links.py)
        same = (
            pl.col("asset_issued").is_null()
            | (pl.col("asset_issued") == "")
            | (pl.col("asset_issued") == pl.col("isin"))
        )
        b3 = b3.filter(pl.col("label").is_in(list(B3_STOCK)) & pl.col("last_date_prior").is_not_null() & same)
        b3 = b3.with_columns(next_session(dates, b3["last_date_prior"]).alias("ex_date"))
        for r in b3.iter_rows(named=True):
            ratio = b3_ratio(r["label"], Fraction(r["factor"]))
            if ratio is None or r["ex_date"] is None:
                continue
            rows.append({"instrument_id": r["instrument_id"], "event_type": B3_STOCK[r["label"]],
                         "data_com": r["last_date_prior"], "ex_date": r["ex_date"], "ratio": ratio,
                         "approved_on": r["approved_on"], "source": "b3_company_events"})  # fmt: skip
    y = _staging(zones, "yahoo_chart", "split")
    if y is not None:
        tick = ids.filter(pl.col("scheme") == "TICKER").select("instrument_id", "value", "vt_from", "vt_to")
        y = y.unique(["ticker", "ex_date", "numerator", "denominator"]).join(tick, left_on="ticker", right_on="value")
        y = y.filter(
            (pl.col("ex_date") > pl.col("vt_from")) & (pl.col("ex_date") <= pl.col("vt_to") + pl.duration(days=10))
        )
        for r in y.iter_rows(named=True):
            ratio = Fraction(r["numerator"], r["denominator"])
            kind = "SPLIT" if ratio > 1 else "REVERSE_SPLIT"
            rows.append({"instrument_id": r["instrument_id"], "event_type": kind, "data_com": None,
                         "ex_date": r["ex_date"], "ratio": ratio, "approved_on": None,
                         "source": "yahoo_chart"})  # fmt: skip
    if not rows:
        return pl.DataFrame()
    return merge_stock(rows)


def merge_stock(rows: list[dict[str, Any]]) -> pl.DataFrame:
    """One event per (instrument, ex-date, ratio) across sources. A B3 BONUS and a Yahoo SPLIT with the same ratio and
    date are the same event; B3's type wins."""
    merged: dict[tuple[Any, Any, Any], dict[str, Any]] = {}
    for r in sorted(rows, key=lambda r: (r["source"] != "b3_company_events",)):
        k = (r["instrument_id"], r["ex_date"], r["ratio"])
        if k in merged:
            m = merged[k]
            if r["source"] not in str(m["sources"]):
                m["sources"] = f"{m['sources']},{r['source']}"
            m["data_com"] = m["data_com"] or r["data_com"]
        else:
            merged[k] = {**r, "sources": r["source"]}
    out = [
        {
            "instrument_id": m["instrument_id"],
            "event_type": m["event_type"],
            "data_com": m["data_com"],
            "ex_date": m["ex_date"],
            "ratio_num": m["ratio"].numerator,  # type: ignore[union-attr]
            "ratio_den": m["ratio"].denominator,  # type: ignore[union-attr]
            "approved_on": m["approved_on"],
            "sources": m["sources"],
        }
        for m in merged.values()
    ]
    return pl.DataFrame(out, schema={"instrument_id": pl.String, "event_type": pl.String, "data_com": pl.Date,
                                     "ex_date": pl.Date, "ratio_num": pl.Int64, "ratio_den": pl.Int64,
                                     "approved_on": pl.Date, "sources": pl.String})  # fmt: skip


def _group(sources: pl.Expr) -> pl.Expr:
    """The source group an event counts in on its day: B3 when B3 reports it, else Yahoo. A day's events are
    checked and applied per group, never summed across groups (Yahoo often reports B3's two-step events as one)."""
    return pl.when(sources.str.contains("b3")).then(pl.lit("b3")).otherwise(pl.lit("yahoo"))


def price_check(events: pl.DataFrame, prices: pl.LazyFrame) -> pl.DataFrame:
    """For each (instrument, ex-date, source group): the net ratio of the day's events, and the raw move
    close(last session before ex) / close(ex). `price_check` = move / net ratio (1 = exact)."""
    closes = (
        prices.filter(pl.col("market_segment") == "lote_padrao")
        .select("instrument_id", "trade_date", pl.col("close").cast(pl.Float64))
        .collect()
    )
    ratio = pl.col("ratio_num").cast(pl.Float64) / pl.col("ratio_den").cast(pl.Float64)
    ev = events.with_columns(_group(pl.col("sources")).alias("_g"))
    day = ev.group_by("instrument_id", "ex_date", "_g").agg(ratio.product().alias("_net"))
    day = day.with_columns(pl.col("ex_date").alias("_t1"), pl.col("ex_date").dt.offset_by("-1d").alias("_t0"))
    day = day.sort("instrument_id", "_t1").join_asof(
        closes.rename({"trade_date": "_t1", "close": "_c_ex"}).sort("instrument_id", "_t1"),
        on="_t1",
        by="instrument_id",
        strategy="forward",
    )
    day = day.sort("instrument_id", "_t0").join_asof(
        closes.rename({"trade_date": "_t0", "close": "_c_before"}).sort("instrument_id", "_t0"),
        on="_t0",
        by="instrument_id",
        strategy="backward",
    )
    day = day.with_columns((pl.col("_c_before") / pl.col("_c_ex")).alias("_move")).select(
        "instrument_id", "ex_date", "_g", "_net", "_move"
    )
    out = ev.join(day, on=["instrument_id", "ex_date", "_g"], how="left")
    return out.with_columns((pl.col("_move") / pl.col("_net")).alias("price_check"))


def agrees(move: pl.Expr, net: pl.Expr) -> pl.Expr:
    """The raw move is closer to the stated ratio than to no event (in log space), and within a factor of 2 of it.
    Prices of distressed issuers keep falling after reverse splits, so a narrow band would reject real events; a
    wrong ratio (100 for 10, a split read as a reverse split) still fails. A ratio within ±20 % of 1 cannot be told
    from noise; it passes when the move is within 10 % of it (RENT3 2019-12, 21:20, moved 0.973 of the ratio)."""
    lm, ln = move.log(), net.log()
    gap = (lm - ln).abs()
    # a small ratio (a 5 % bonus) sits inside one day's price noise: it passes when the move is within 10 % of it
    small = (ln.abs() < SMALL_LOG) & (gap <= SMALL_GAP)
    return ((gap < lm.abs()) & (gap <= math.log(2))) | small


def status(sources: pl.Expr, move: pl.Expr, net: pl.Expr) -> pl.Expr:
    agree = agrees(move, net).fill_null(False)
    two = sources.str.contains(",")
    return (
        pl.when(two | (sources.str.contains("b3") & agree)).then(pl.lit("confirmed"))
        .when(agree).then(pl.lit("price_only"))
        .otherwise(pl.lit("candidate"))
    )  # fmt: skip


def rights_events(zones: Zones, dates: pl.Series) -> pl.DataFrame:
    """B3 subscriptions: ratio = 1 + percentage/100 (shares after full subscription), price in cash_per_share."""
    s = _staging(zones, "b3_company_events", "subscription")
    if s is None or not s.height:
        return pl.DataFrame()
    isin = _ids(zones).filter(pl.col("scheme") == "ISIN").select("instrument_id", pl.col("value").alias("isin"))
    s = s.unique(["isin", "percentage", "price_unit", "last_date_prior"]).join(isin.unique("isin"), on="isin")
    s = s.filter(pl.col("last_date_prior").is_not_null())
    rows = []
    for r in s.iter_rows(named=True):
        ratio = 1 + Fraction(r["percentage"]) / 100
        rows.append(
            {
                "instrument_id": r["instrument_id"],
                "event_type": "RIGHTS",
                "data_com": r["last_date_prior"],
                "ratio_num": ratio.numerator,
                "ratio_den": ratio.denominator,
                "cash_per_share": r["price_unit"],
                "approved_on": r["approved_on"],
                "payment_date": r["subscription_date"],
                "sources": "b3_company_events",
            }
        )
    schema = {
        "instrument_id": pl.String,
        "event_type": pl.String,
        "data_com": pl.Date,
        "ratio_num": pl.Int64,
        "ratio_den": pl.Int64,
        "cash_per_share": CASH,
        "approved_on": pl.Date,
        "payment_date": pl.Date,
        "sources": pl.String,
    }
    out = pl.DataFrame(rows, schema=schema)
    return out.with_columns(
        next_session(dates, out["data_com"]).alias("ex_date"),
        pl.lit(None, dtype=pl.Float64).alias("price_check"),
        pl.lit("reported").alias("status"),
        pl.lit(None, dtype=KT).alias("kt_published_at"),
    )


def latest_cash_snapshot(zones: Zones, b3: pl.DataFrame) -> pl.DataFrame:
    """The rows of each cash history (root, trading name) as served by its latest run. Identical rows are distinct
    installments (GRND 2025-12-26: two of 0,221690166), so rows are never collapsed by value; staging keeps every
    snapshot of this dataset whole (no changed-row staging) for that reason."""
    from fin.store.manifest import Manifest

    runs = (
        Manifest(zones.manifest)
        .read()
        .filter((pl.col("source_id") == "b3_company_events") & (pl.col("dataset_id") == "cash"))
        .select("raw_sha256", pl.col("ingest_run_id").alias("_run"))
        .unique("raw_sha256", keep="first")
    )
    b3 = b3.join(runs, on="raw_sha256", how="left")
    latest = pl.col("_run").max().over("root", "trading_name")
    return b3.filter(pl.col("_run") == latest).drop("_run")


def cash_events(zones: Zones, dates: pl.Series) -> pl.DataFrame:
    frames: list[pl.DataFrame] = []
    ids = _ids(zones)
    b3 = _staging(zones, "b3_company_events", "cash_event")
    if b3 is not None and b3.height:
        b3 = latest_cash_snapshot(zones, b3)
        cls = share_classes(zones)
        b3 = b3.join(cls, on=["root", "type_stock"], how="inner").filter(
            (pl.col("last_date_prior") >= pl.col("first_trade")) & (pl.col("last_date_prior") <= pl.col("last_trade"))
        )
        frames.append(
            b3.select(
                "instrument_id",
                pl.col("kind").replace_strict(B3_CASH, default="OTHER_CASH").alias("event_type"),
                pl.col("last_date_prior").alias("data_com"),
                (pl.col("value_cash") / pl.col("quoted_per_shares").cast(CASH)).cast(CASH).alias("cash_per_share"),
                "approved_on",
                pl.lit(None, dtype=pl.Date).alias("payment_date"),
                pl.lit("b3_company_events").alias("sources"),
                pl.lit(None, dtype=KT).alias("kt_published_at"),
            )
        )
    f = _staging(zones, "b3_fundosnet", "distribution")
    if f is not None and f.height:
        isin = (
            ids.filter(pl.col("scheme") == "ISIN").select("instrument_id", pl.col("value").alias("isin")).unique("isin")
        )
        f = f.unique(["isin", "kind", "base_date", "value_per_quota", "payment_date"]).join(
            isin, on="isin", how="inner"
        )
        listing = _staging(zones, "b3_fundosnet", "listing")
        if listing is not None:
            first = listing.group_by("doc_id").agg(pl.col("delivered_at").min().alias("kt_published_at"))
            f = f.join(first, on="doc_id", how="left")
        else:
            f = f.with_columns(pl.lit(None, dtype=KT).alias("kt_published_at"))
        frames.append(
            f.select(
                "instrument_id",
                pl.col("kind")
                .replace_strict({"rendimento": "INCOME", "amortizacao": "AMORTIZATION"})
                .alias("event_type"),
                pl.col("base_date").alias("data_com"),
                pl.col("value_per_quota").cast(CASH).alias("cash_per_share"),
                pl.lit(None, dtype=pl.Date).alias("approved_on"),
                "payment_date",
                pl.lit("b3_fundosnet").alias("sources"),
                "kt_published_at",
            )
        )
    if not frames:
        return pl.DataFrame()
    out = pl.concat(frames)
    return out.with_columns(next_session(dates, out["data_com"]).alias("ex_date"))


def share_classes(zones: Zones) -> pl.DataFrame:
    """(issuer root, share class) -> instrument and its trading span, from COTAHIST: the root is the first four
    letters of a modern ticker (XXXX3), the class the first word of ESPECI (ON, PN, PNA, UNT…)."""
    q = (
        pl.scan_parquet(zones.staging / "b3_cotahist" / "quote" / "**" / "*.parquet", hive_partitioning=False)
        .filter((pl.col("tpmerc") == 10) & pl.col("ticker").str.contains(r"^[A-Z0-9]{4}\d{1,2}$"))
        .select(
            pl.col("ticker").str.slice(0, 4).alias("root"),
            pl.col("especi").str.extract(r"^(\S+)").alias("type_stock"),
            "isin",
        )
        .unique()
        .collect()
    )
    ids = (
        _ids(zones)
        .filter(pl.col("scheme").is_in(["ISIN", "B3_CODISI"]))
        .select("instrument_id", pl.col("value").alias("isin"))
    )
    inst = pl.read_parquet(zones.core / "instrument" / "instrument.parquet").select(
        "instrument_id", "first_trade", "last_trade"
    )
    return (
        q.join(ids, on="isin")
        .join(inst, on="instrument_id")
        .select("root", "type_stock", "instrument_id", "first_trade", "last_trade")
        .unique()
    )


def factors(events: pl.DataFrame, prices: pl.LazyFrame) -> pl.DataFrame:
    usable = events.filter(
        (pl.col("ratio_num").is_null() & pl.col("cash_per_share").is_not_null())
        | pl.col("status").is_in(["confirmed", "price_only"])
        | (pl.col("event_type") == "RIGHTS")
    )
    closes = (
        prices.filter(pl.col("market_segment") == "lote_padrao")
        .select("instrument_id", "trade_date", pl.col("close").cast(pl.Float64))
        .collect()
        .sort("instrument_id", "trade_date")
    )
    rights = (
        usable.filter(pl.col("event_type") == "RIGHTS")
        .sort("instrument_id", "data_com")
        .join_asof(closes, left_on="data_com", right_on="trade_date", by="instrument_id", strategy="backward")
        .with_columns((pl.col("ratio_num").cast(pl.Float64) / pl.col("ratio_den").cast(pl.Float64)).alias("_r"))
        # theoretical ex-rights price over the cum price: (P + (r-1)·S) / (r·P); only when S < P
        .with_columns(
            ((pl.col("close") + (pl.col("_r") - 1) * pl.col("cash_per_share").cast(pl.Float64))
             / (pl.col("_r") * pl.col("close"))).alias("f")
        )
        .filter(pl.col("cash_per_share").cast(pl.Float64) < pl.col("close"))
        .group_by("instrument_id", "ex_date")
        .agg(pl.col("f").product().alias("rights_factor"))
    )  # fmt: skip
    usable = usable.filter(pl.col("event_type") != "RIGHTS")
    cash = (
        usable.filter(pl.col("cash_per_share").is_not_null() & pl.col("data_com").is_not_null())
        .sort("instrument_id", "data_com")
        .join_asof(closes, left_on="data_com", right_on="trade_date", by="instrument_id", strategy="backward")
        .with_columns((1 - pl.col("cash_per_share").cast(pl.Float64) / pl.col("close")).alias("f"))
        .filter(pl.col("f").is_between(0.0, 1.0, closed="right"))
        .group_by("instrument_id", "ex_date")
        .agg(pl.col("f").product().alias("cash_factor"))
    )
    stock = usable.filter(pl.col("ratio_num").is_not_null()).with_columns(_group(pl.col("sources")).alias("_g"))
    # one source group per day: B3's events when B3 reports any that day, else Yahoo's
    stock = stock.filter(pl.col("_g") == pl.col("_g").min().over("instrument_id", "ex_date"))
    split = stock.group_by("instrument_id", "ex_date").agg(
        (pl.col("ratio_den").cast(pl.Float64) / pl.col("ratio_num").cast(pl.Float64)).product().alias("split_factor")
    )
    out = split.join(cash, on=["instrument_id", "ex_date"], how="full", coalesce=True)
    out = out.join(rights, on=["instrument_id", "ex_date"], how="full", coalesce=True)
    return out.with_columns(
        pl.col("split_factor").fill_null(1.0),
        (pl.col("cash_factor").fill_null(1.0) * pl.col("rights_factor").fill_null(1.0)).alias("cash_factor"),
    ).select(FACTOR.names)


def build(zones: Zones, run: IngestRun | None = None) -> dict[str, int]:
    if not (zones.core / "price_daily").exists():
        return {}
    dates = sessions(zones)
    prices = pl.scan_parquet(zones.core / "price_daily" / "*.parquet")
    stock = stock_events(zones, dates)
    if stock.height:
        stock = price_check(stock, prices)
        stock = stock.with_columns(status(pl.col("sources"), pl.col("_move"), pl.col("_net")).alias("status")).drop(
            "_g", "_net", "_move"
        )
        stock = stock.with_columns(
            pl.lit(None, dtype=CASH).alias("cash_per_share"),
            pl.lit(None, dtype=pl.Date).alias("payment_date"),
            pl.lit(None, dtype=KT).alias("kt_published_at"),
        )
    cash = cash_events(zones, dates)
    if cash.height:
        cash = cash.with_columns(
            pl.lit(None, dtype=pl.Int64).alias("ratio_num"),
            pl.lit(None, dtype=pl.Int64).alias("ratio_den"),
            pl.lit(None, dtype=pl.Float64).alias("price_check"),
            pl.lit("reported").alias("status"),
        )
    rights = rights_events(zones, dates)
    cols = [c for c in EVENT.names if c != "event_id"]
    allev = pl.concat([f.select(cols) for f in (stock, cash, rights) if f.height], how="vertical_relaxed")
    allev = allev.filter(pl.col("ex_date").is_not_null()).sort("instrument_id", "ex_date", "event_type", "sources")
    allev = allev.with_columns(
        (
            pl.col("instrument_id") + "|" + pl.col("event_type") + "|" + pl.col("ex_date").cast(pl.String) + "|"
            + pl.int_range(pl.len()).over("instrument_id", "event_type", "ex_date").cast(pl.String)
        ).alias("event_id")
    ).select(EVENT.names)  # fmt: skip
    good, bad = EVENT.split(allev)
    write_parquet(good, zones.core / "corporate_event" / "corporate_event.parquet")
    q = zones.quarantine / "core" / "corporate_event.parquet"
    if bad.height:
        write_parquet(bad, q)
    else:
        q.unlink(missing_ok=True)
    fac = factors(good, prices)
    write_parquet(
        fac.sort("instrument_id", "ex_date"), zones.derived / "adjustment_factor" / "adjustment_factor.parquet"
    )
    from fin.core import links

    out = {"events": good.height, "events:quarantined": bad.height, "factors": fac.height, **links.build(zones, run)}
    if run is not None:
        run.count("core.corporate_event", in_=allev.height, out=good.height, quarantined=bad.height)
    return out


def adjusted_close(zones: Zones, instrument_id: str, cash: bool = True) -> pl.DataFrame:
    """Unadjusted closes with backward split (and cash) adjustment to today's basis: derived on read."""
    prices = (
        pl.scan_parquet(zones.core / "price_daily" / "*.parquet")
        .filter((pl.col("instrument_id") == instrument_id) & (pl.col("market_segment") == "lote_padrao"))
        .select("trade_date", pl.col("close").cast(pl.Float64))
        .collect()
        .sort("trade_date")
    )
    f = pl.read_parquet(zones.derived / "adjustment_factor" / "adjustment_factor.parquet").filter(
        pl.col("instrument_id") == instrument_id
    )
    f = f.with_columns((pl.col("split_factor") * (pl.col("cash_factor") if cash else 1.0)).alias("f")).sort("ex_date")
    # the factor of an ex-date applies to every session before it: cumulative product from the latest backwards
    f = f.with_columns(pl.col("f").reverse().cum_prod().reverse().alias("cum"))
    adj = prices.join_asof(f.select("ex_date", "cum"), left_on="trade_date", right_on="ex_date", strategy="forward",
                           allow_exact_matches=False)  # fmt: skip
    return adj.with_columns((pl.col("close") * pl.col("cum").fill_null(1.0)).alias("adj_close")).select(
        "trade_date", "close", "adj_close"
    )
