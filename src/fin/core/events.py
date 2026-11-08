"""Corporate events and price adjustment factors (PLAN §4.3.3, §4.7; ADR-0016).

`core/corporate_event` holds one row per event of one instrument:
- **stock events** from B3's Supplement (by ISIN; tier U) and Yahoo (by ticker on the date; tier U), merged on
  (instrument, ex-date); ratio = new shares per old share, exact;
- **cash events** from B3's cash history (by issuer root and share class) and Fundos.NET (FII notices, by ISIN);
  `cash_per_share` in BRL per one share.

Each stock event carries its evidence: which sources report it, and whether the unadjusted prices moved by the
stated ratio across the ex-date (`price_check`: the close of the last session with the right over the first session
without it, divided by the ratio). The status is `conflicting` when the price contradicts the ratio (it did not
move although the ratio is large enough to show, whatever the sources say: adjusting would put a jump into the
adjusted series), else `confirmed` (two sources, or B3 and the price check), `price_only` (one source, the price
check agrees), else `unpriced`, `official` or `unsupported` (see `status`): every event is decided. Only
`confirmed`, `price_only` and `official` events enter the adjustment factors. The
check is made on the day's net ratio per source group (B3 may record one operation as two same-day events), and
passes when the move is closer to the ratio than to no event, within a factor of 2.

The ex-date is the first B3 session after the data-com, taken from the sessions in `price_daily` (B3's own calendar);
Yahoo dates are already ex-dates.

`derived/adjustment_factor` (rebuilt, never the truth, PLAN invariant 6): per instrument and ex-date, the factor that
multiplies prices **before** the ex-date: 1/ratio for stock events; (1 − cash / close of the data-com) for cash.
"""

from __future__ import annotations

import math
from datetime import date
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
TYPES = (
    "DIVIDEND", "JCP", "INCOME", "AMORTIZATION", "OTHER_CASH", "BONUS", "SPLIT", "REVERSE_SPLIT", "RIGHTS",
    "QUOTE_BASIS",
)  # fmt: skip

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
            "DIVIDEND, JCP, INCOME, AMORTIZATION, OTHER_CASH, BONUS, SPLIT, REVERSE_SPLIT, RIGHTS, QUOTE_BASIS",
            "tipo",
            nullable=False,
        ),
        Column(
            "data_com", pl.Date, "last session with the right (null when only Yahoo reports it)", "data com", "date"
        ),
        Column("ex_date", pl.Date, "first session without the right", "data ex", "date", nullable=False),
        Column(
            "ex_date_reported",
            pl.Date,
            "stock events: the ex-date the source reported, when the price moved the event to another session",
            "data ex informada",
            "date",
        ),
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
            "applied: confirmed, price_only, official; not: conflicting, unpriced, unsupported; cash: reported",
            "situação",
            nullable=False,
        ),
        Column("ipe_protocol", pl.String, "CVM IPE document that announces it (stock events)", "protocolo IPE"),
        Column("ipe_link", pl.String, "its download link", "link IPE"),
        Column("ipe_delivered_on", pl.Date, "its delivery date", "entrega IPE", "date"),
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
            "product of 1/ratio of the day's stock events, and of spin-offs' 1 - (shares received x their first close)"
            " / cum close",
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


MAX_GAP_DAYS = 90  # beyond this the price move between two sessions says nothing about the event


def ipca_level(zones: Zones) -> pl.DataFrame:
    """IPCA index (IBGE, SIDRA 1737 v2266) per month: the level at the start (`i0`, end of the previous month) and
    at the end (`i1`) of each month, to interpolate a daily level geometrically."""
    path = zones.core / "series_observation"
    if not path.exists():
        return pl.DataFrame(schema={"month": pl.Date, "i0": pl.Float64, "i1": pl.Float64})
    s = (
        pl.scan_parquet(path / "*.parquet")
        .filter(pl.col("series_id") == "ibge_sidra:1737/v2266")
        .select((pl.col("vt_reference") + "-01").str.to_date().alias("month"), pl.col("value").cast(pl.Float64))
        .collect()
        .unique("month", keep="last")
        .sort("month")
    )
    return s.select("month", pl.col("value").shift(1).alias("i0"), pl.col("value").alias("i1")).drop_nulls()


def _level(d: str, ipca: pl.DataFrame, frame: pl.DataFrame) -> pl.DataFrame:
    """Adds `_lv<d>`: the IPCA level interpolated on date column `d` (null outside the index)."""
    m = ipca.rename({"month": f"_m{d}", "i0": f"_i0{d}", "i1": f"_i1{d}"})
    f = frame.with_columns(pl.col(d).dt.truncate("1mo").alias(f"_m{d}")).join(m, on=f"_m{d}", how="left")
    frac = pl.col(d).dt.day().cast(pl.Float64) / pl.col(d).dt.month_end().dt.day().cast(pl.Float64)
    lv = pl.col(f"_i0{d}") * (pl.col(f"_i1{d}") / pl.col(f"_i0{d}")) ** frac
    return f.with_columns(lv.alias(f"_lv{d}")).drop(f"_m{d}", f"_i0{d}", f"_i1{d}")


def price_check(events: pl.DataFrame, prices: pl.LazyFrame, ipca: pl.DataFrame | None = None) -> pl.DataFrame:
    """For each (instrument, ex-date, source group): the net ratio of the day's events, and the move
    close(last session before ex) / close(first session from ex), both in BRL (a currency change is not an event)
    and corrected for IPCA inflation between the two sessions (1986-94 sessions can be months apart at 20-80 % a
    month). `price_check` = move / net ratio (1 = exact). `_priced`: the line traded on both sides; the move is
    null when the two sessions are more than 90 days apart."""
    brl = pl.col("brl_num").cast(pl.Float64) / pl.col("brl_den").cast(pl.Float64)
    closes = (
        prices.filter(pl.col("market_segment") == "lote_padrao")
        .select("instrument_id", "trade_date", (pl.col("close").cast(pl.Float64) * brl).alias("close"))
        .collect()
    )
    ratio = pl.col("ratio_num").cast(pl.Float64) / pl.col("ratio_den").cast(pl.Float64)
    ev = events.with_columns(_group(pl.col("sources")).alias("_g"))
    day = ev.group_by("instrument_id", "ex_date", "_g").agg(ratio.product().alias("_net"))
    day = day.with_columns(pl.col("ex_date").alias("_t1"), pl.col("ex_date").dt.offset_by("-1d").alias("_t0"))
    day = day.sort("instrument_id", "_t1").join_asof(
        closes.with_columns(pl.col("trade_date").alias("_d1"))
        .rename({"trade_date": "_t1", "close": "_c_ex"})
        .sort("instrument_id", "_t1"),
        on="_t1",
        by="instrument_id",
        strategy="forward",
    )
    day = day.sort("instrument_id", "_t0").join_asof(
        closes.with_columns(pl.col("trade_date").alias("_d0"))
        .rename({"trade_date": "_t0", "close": "_c_before"})
        .sort("instrument_id", "_t0"),
        on="_t0",
        by="instrument_id",
        strategy="backward",
    )
    if ipca is not None and ipca.height:
        day = _level("_d1", ipca, _level("_d0", ipca, day))
        infl = (pl.col("_lv_d1") / pl.col("_lv_d0")).fill_null(1.0)
    else:
        infl = pl.lit(1.0)
    gap = (pl.col("_d1") - pl.col("_d0")).dt.total_days()
    day = day.with_columns(
        (pl.col("_d0").is_not_null() & pl.col("_d1").is_not_null()).alias("_priced"),
        pl.when(gap <= MAX_GAP_DAYS).then(pl.col("_c_before") / pl.col("_c_ex") * infl).alias("_move"),
    ).select("instrument_id", "ex_date", "_g", "_net", "_move", "_priced")
    out = ev.join(day, on=["instrument_id", "ex_date", "_g"], how="left")
    return out.with_columns((pl.col("_move") / pl.col("_net")).alias("price_check"))


REDATE_DAYS = 30


def redate(stock: pl.DataFrame, prices: pl.LazyFrame) -> pl.DataFrame:
    """An event whose price does not agree on its reported ex-date is moved to the session within 30 days where
    the price did move by its ratio (one-day move in BRL; the closest such session wins). Yahoo's split dates are
    often a few days off, and so are some of B3's oldest records: the price fixes the ex-date. The reported date is
    kept in `ex_date_reported`; re-dated events get their price check from that session."""
    brl = pl.col("brl_num").cast(pl.Float64) / pl.col("brl_den").cast(pl.Float64)
    day = (
        prices.filter(pl.col("market_segment") == "lote_padrao")
        .select("instrument_id", "trade_date", (pl.col("close").cast(pl.Float64) * brl).alias("c"))
        .sort("instrument_id", "trade_date")
        .with_columns((pl.col("c").shift(1).over("instrument_id") / pl.col("c")).alias("_m1"))
        .filter(pl.col("_m1").is_not_null())
        .select("instrument_id", "trade_date", "_m1")
    )
    ratio = pl.col("ratio_num").cast(pl.Float64) / pl.col("ratio_den").cast(pl.Float64)
    s = stock.with_row_index("_r").with_columns(pl.col("ex_date").alias("ex_date_reported"))
    off = s.filter(~agrees(pl.col("_move"), pl.col("_net")).fill_null(False)).select(
        "_r", "instrument_id", "ex_date", ratio.alias("_rt")
    )
    ids = off["instrument_id"].unique().to_list()
    cand = (
        off.lazy()
        .join(day.filter(pl.col("instrument_id").is_in(ids)), on="instrument_id")
        .filter(
            ((pl.col("trade_date") - pl.col("ex_date")).dt.total_days().abs() <= REDATE_DAYS)
            & (pl.col("trade_date") != pl.col("ex_date"))
            & agrees(pl.col("_m1"), pl.col("_rt"))
            & (pl.col("_rt").log().abs() >= SMALL_LOG)  # a 5 % move is found on any day: never re-dated
        )
        .with_columns((pl.col("trade_date") - pl.col("ex_date")).dt.total_days().abs().alias("_dist"))
        .sort("_r", "_dist")
        .unique("_r", keep="first")
        .select("_r", pl.col("trade_date").alias("_new"), pl.col("_m1").alias("_newmove"))
        .collect()
    )
    s = s.join(cand, on="_r", how="left")
    return (
        s.with_columns(
            pl.coalesce("_new", "ex_date").alias("ex_date"),
            pl.when(pl.col("_new").is_not_null() & (pl.col("_new") <= pl.col("data_com")))
            .then(None)
            .otherwise(pl.col("data_com"))
            .alias("data_com"),
            pl.when(pl.col("_new").is_not_null()).then(pl.col("_newmove")).otherwise(pl.col("_move")).alias("_move"),
            pl.when(pl.col("_new").is_not_null()).then(ratio).otherwise(pl.col("_net")).alias("_net"),
            (pl.col("_priced") | pl.col("_new").is_not_null()).alias("_priced"),
        )
        .with_columns(
            pl.when(pl.col("_new").is_not_null())
            .then(pl.col("_move") / pl.col("_net"))
            .otherwise(pl.col("price_check"))
            .alias("price_check")
        )
        .drop("_r", "_new", "_newmove")
    )


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


IPE_WORDS = {  # event type -> words of the IPE subject that announce it (regex, lower case, accents kept)
    "BONUS": "bonifica",
    "SPLIT": "desdobr|bonifica",  # Yahoo reports bonuses as splits (ITUB 2025-03)
    "REVERSE_SPLIT": "grupament",
}
IPE_CATEGORIES = ("Fato Relevante", "Aviso aos Acionistas", "Comunicado ao Mercado", "Assembleia")
IPE_BEFORE_DAYS = 90
IPE_AFTER_DAYS = 10


def ipe_evidence(zones: Zones, stock: pl.DataFrame) -> pl.DataFrame:
    """For each stock event, the earliest IPE document of the same issuer (CNPJ via `issuer_instrument`), of an
    announcing category, whose subject names the event type, delivered from 90 days before the data-com (or
    ex-date) to 10 days after the ex-date. Adds `cvm_ipe` to the sources of the events it proves."""
    docs = _staging(zones, "cvm_ipe", "document")
    link = zones.core / "issuer_instrument" / "issuer_instrument.parquet"
    issuer = zones.core / "issuer" / "issuer.parquet"
    empty = stock.with_columns(
        pl.lit(None, dtype=pl.String).alias("ipe_protocol"),
        pl.lit(None, dtype=pl.String).alias("ipe_link"),
        pl.lit(None, dtype=pl.Date).alias("ipe_delivered_on"),
    )
    if docs is None or not link.exists() or not issuer.exists():
        return empty
    cnpj = pl.read_parquet(link).join(pl.read_parquet(issuer).select("issuer_id", "cnpj"), on="issuer_id")
    cnpj = cnpj.select("instrument_id", "cnpj").unique("instrument_id")
    text = (pl.col("subject").fill_null("") + " " + pl.col("doc_type").fill_null("")).str.to_lowercase()
    docs = docs.filter(pl.col("category").is_in(IPE_CATEGORIES)).select(
        pl.col("cnpj").str.replace_all(r"\D", "").alias("cnpj"),
        "delivered_on",
        pl.col("protocol").alias("ipe_protocol"),
        pl.col("link").alias("ipe_link"),
        text.alias("_text"),
    )
    ev = stock.with_row_index("_r").join(cnpj, on="instrument_id", how="left")
    ev = ev.with_columns(
        pl.col("event_type").replace_strict(IPE_WORDS, default=None).alias("_word"),
        pl.coalesce("data_com", "ex_date").dt.offset_by(f"-{IPE_BEFORE_DAYS}d").alias("_lo"),
        pl.col("ex_date").dt.offset_by(f"{IPE_AFTER_DAYS}d").alias("_hi"),
    )
    cand = (
        ev.filter(pl.col("_word").is_not_null())
        .join(docs, on="cnpj")
        .filter(
            pl.col("delivered_on").is_between(pl.col("_lo"), pl.col("_hi"))
            & pl.col("_text").str.contains(pl.col("_word"))
        )
    )
    best = (
        cand.sort("delivered_on")
        .unique("_r", keep="first")
        .select(
            "_r",
            "ipe_protocol",
            "ipe_link",
            pl.col("delivered_on").alias("ipe_delivered_on"),
            (pl.col("_text").str.contains("bonifica") & ~pl.col("_text").str.contains("desdobr")).alias("_is_bonus"),
        )
    )
    out = ev.join(best, on="_r", how="left").sort("_r")
    out = out.with_columns(
        pl.when(pl.col("ipe_link").is_not_null())
        .then(pl.col("sources") + ",cvm_ipe")
        .otherwise(pl.col("sources"))
        .alias("sources"),
        # Yahoo reports a bonus as a split; the filing says which
        pl.when(pl.col("_is_bonus").fill_null(False) & (pl.col("event_type") == "SPLIT"))
        .then(pl.lit("BONUS"))
        .otherwise(pl.col("event_type"))
        .alias("event_type"),
    )
    return out.drop("_r", "cnpj", "_word", "_lo", "_hi", "_is_bonus")


def contradicts(move: pl.Expr, net: pl.Expr) -> pl.Expr:
    """The price did not move although the ratio is large enough to show: the move is closer to no event than to the
    ratio (in log space) and the ratio is beyond ±20 % of 1. ITUB4 2011-11-01: B3 and a filing report a 1:100
    reverse split, but it was simultaneous with a 100:1 split (net 1) and the price moved by 1.02."""
    lm, ln = move.log(), net.log()
    return (lm.abs() < (lm - ln).abs()) & (ln.abs() >= SMALL_LOG)


APPLIED = ("confirmed", "price_only", "official")


def status(sources: pl.Expr, move: pl.Expr, net: pl.Expr, priced: pl.Expr | None = None) -> pl.Expr:
    """Every stock event is decided; `APPLIED` statuses adjust prices, the others do not:
    - `conflicting`: the price contradicts the ratio, whatever the sources say (rejected);
    - `confirmed`: two sources, or B3 and an agreeing price; `price_only`: one source and an agreeing price;
    - `unpriced`: the line did not trade on one side of the ex-date, so no price of it is affected;
    - `official`: B3 (the registrar's record) alone with an inconclusive price (sessions far apart, or a move
      between the bands): applied;
    - `unsupported`: Yahoo (tier U) alone with an inconclusive price: rejected."""
    agree = agrees(move, net).fill_null(False)
    two = sources.str.contains(",")
    has_price = priced if priced is not None else move.is_not_null()
    return (
        pl.when(contradicts(move, net).fill_null(False)).then(pl.lit("conflicting"))
        .when(two | (sources.str.contains("b3") & agree)).then(pl.lit("confirmed"))
        .when(agree).then(pl.lit("price_only"))
        .when(~has_price.fill_null(False)).then(pl.lit("unpriced"))
        .when(sources.str.contains("b3")).then(pl.lit("official"))
        .otherwise(pl.lit("unsupported"))
    )  # fmt: skip


def quote_basis_events(prices: pl.LazyFrame, stock: pl.DataFrame) -> pl.DataFrame:
    """COTAHIST's own evidence of a change of share basis (ADR-0016 addendum). At a session where FATCOT changes
    and the quoted price (per FATCOT shares, in BRL) is continuous (between 0.5 and 2 times the previous session's)
    while the price per share jumps by the factor, the line now quotes FATCOT_old/FATCOT_new old shares as one: a
    regrouping (MGEL4 2004-06-29: 4.90 per 1,000 to 4.95 per share), or, in the 1987-89 mass changes, a flag that
    changed while prices stayed per lot. Either way the per-share series must be continuous across it. A
    `QUOTE_BASIS` event (ratio FATCOT_new : FATCOT_old) is made unless an applied stock event of about that size
    (within 2x) is within 5 days."""
    brl = pl.col("brl_num").cast(pl.Float64) / pl.col("brl_den").cast(pl.Float64)
    p = (
        prices.filter(pl.col("market_segment") == "lote_padrao")
        .select(
            "instrument_id",
            "trade_date",
            pl.col("quote_factor").cast(pl.Int64).alias("qf"),
            (pl.col("close").cast(pl.Float64) * brl).alias("u"),
        )
        .sort("instrument_id", "trade_date")
        .with_columns(
            pl.col("qf").shift(1).over("instrument_id").alias("qf0"),
            pl.col("u").shift(1).over("instrument_id").alias("u0"),
            pl.col("trade_date").shift(1).over("instrument_id").alias("d0"),
        )
        .filter(pl.col("qf0").is_not_null() & (pl.col("qf") != pl.col("qf0")) & (pl.col("u0") > 0))
        .collect()
    )
    unit = pl.col("u") / pl.col("u0")
    lot = unit * pl.col("qf") / pl.col("qf0")
    p = p.filter(lot.is_between(0.5, 2.0) & ~unit.is_between(0.5, 2.0))
    if stock.height:
        applied = stock.filter(pl.col("status").is_in(APPLIED) & pl.col("ratio_num").is_not_null()).select(
            "instrument_id",
            pl.col("ex_date").alias("_ex"),
            (pl.col("ratio_num").cast(pl.Float64) / pl.col("ratio_den").cast(pl.Float64)).alias("_r"),
        )
        near = (
            p.join(applied, on="instrument_id")
            .filter(
                ((pl.col("_ex") - pl.col("trade_date")).dt.total_days().abs() <= 5)
                & ((pl.col("_r") * pl.col("qf0") / pl.col("qf")).log().abs() <= math.log(2))
            )
            .select("instrument_id", "trade_date")
            .unique()
        )
        p = p.join(near, on=["instrument_id", "trade_date"], how="anti")
    return p.select(
        "instrument_id",
        pl.lit("QUOTE_BASIS").alias("event_type"),
        pl.col("d0").alias("data_com"),
        pl.col("trade_date").alias("ex_date"),
        pl.col("qf").alias("ratio_num"),
        pl.col("qf0").alias("ratio_den"),
        pl.lit("b3_cotahist").alias("sources"),
        (1 / lot).alias("price_check"),
        pl.lit("confirmed").alias("status"),
    )


IMPLIED_MIN = 1.25  # smallest ratio an implied event may have: below it, one day's price noise looks the same
IMPLIED_NO_FILING = 3.0  # a one-day move of 3x or more needs no filing: no market moves a share that far


def _snap(s: float) -> tuple[int, int] | None:
    """New shares per old as a simple fraction near `s` (within 5 %; within 10 % for ratios of 10 or more)."""
    from fractions import Fraction

    big = max(s, 1 / s)
    f = Fraction(big).limit_denominator(10) if big < 10 else Fraction(round(big))
    if f <= 0 or abs(float(f) / big - 1) > (0.10 if big >= 10 else 0.05):
        return None
    return (f.numerator, f.denominator) if s >= 1 else (f.denominator, f.numerator)


def implied_events(zones: Zones, prices: pl.LazyFrame, fac: pl.DataFrame) -> pl.DataFrame:
    """Stock events no source lists but the official prices and Yahoo agree on (ADR-0016 addendum): a level shift
    of Yahoo's split-adjusted close against ours (quality check `cotahist_vs_yahoo`, run on the factors so far)
    of at least 1.25, matched (within 30 % in log) by a one-day move of B3's raw close in BRL that our factors leave
    in place. It is kept when a CVM IPE filing announces a bonus, split or regrouping around it, or when the move
    is 3x or more. The ratio is the simple fraction nearest Yahoo's step; the ex-date is the day of the move."""
    from fin.quality.findings import cotahist_vs_yahoo

    leads = cotahist_vs_yahoo(zones)
    if not leads.height:
        return pl.DataFrame()
    leads = leads.select(
        pl.col("entity_id").str.split(":").list.first().alias("instrument_id"),
        pl.col("vt").alias("month"),
        pl.col("observed").cast(pl.Float64).alias("s"),
    ).filter((pl.col("s") > 0) & (pl.col("s").log().abs() >= math.log(IMPLIED_MIN)))
    if not leads.height:
        return pl.DataFrame()
    brl = pl.col("brl_num").cast(pl.Float64) / pl.col("brl_den").cast(pl.Float64)
    day = (
        prices.filter(
            (pl.col("market_segment") == "lote_padrao")
            & pl.col("instrument_id").is_in(leads["instrument_id"].unique().to_list())
        )
        .select("instrument_id", "trade_date", (pl.col("close").cast(pl.Float64) * brl).alias("c"))
        .sort("instrument_id", "trade_date")
        .with_columns(
            (pl.col("c") / pl.col("c").shift(1)).over("instrument_id").log().alias("lr"),
            pl.col("trade_date").shift(1).over("instrument_id").alias("d0"),
        )
        .collect()
        .join(fac.select("instrument_id", pl.col("ex_date").alias("trade_date"), "split_factor"),
              on=["instrument_id", "trade_date"], how="left")
        .filter(pl.col("split_factor").fill_null(1.0) == 1.0)  # a day our factors already adjust is not a miss
    )  # fmt: skip
    ls = pl.col("s").log()
    j = (
        leads.join(day, on="instrument_id")
        .filter(
            pl.col("trade_date").is_between(
                pl.col("month").dt.offset_by("-1mo"), pl.col("month").dt.offset_by("1mo").dt.month_end()
            )
            & ((pl.col("lr") + ls).abs() <= 0.3 * ls.abs())
        )
        .sort("instrument_id", "month", (pl.col("lr") + ls).abs())
        .unique(["instrument_id", "month"], keep="first")
    )
    rows = []
    for r in j.iter_rows(named=True):
        snapped = _snap(r["s"])
        if snapped is None:
            continue
        num, den = snapped
        rows.append(
            {
                "instrument_id": r["instrument_id"],
                "event_type": "REVERSE_SPLIT" if num < den else ("BONUS" if num / den < 2 else "SPLIT"),
                "data_com": r["d0"],
                "ex_date": r["trade_date"],
                "ratio_num": num,
                "ratio_den": den,
                "sources": "b3_cotahist,yahoo_chart",
                "price_check": math.exp(-r["lr"]) / (num / den),
                "_big": max(r["s"], 1 / r["s"]) >= IMPLIED_NO_FILING,
            }
        )
    if not rows:
        return pl.DataFrame()
    ev = ipe_evidence(zones, pl.DataFrame(rows))
    ev = ev.filter(pl.col("sources").str.contains("cvm_ipe") | pl.col("_big")).drop("_big")
    return ev.with_columns(pl.lit("confirmed").alias("status"), pl.col("ex_date").alias("ex_date_reported"))


IMPLIED_IPE_MIN = 3.0  # a one-day move this large on a day no factor adjusts is a candidate stock event
# without a filing, a move of 10x or more is kept only at a conventional ratio and within this of it: 2 % for a
# regrouping (prices jump), 0.5 % for a split (prices fall, as they also do in a collapse); any large move lies within
# 2 % of some integer, so the ratio set matters (TRADE DESK "1:99", CABLE ONE "1:194" are not kept on price alone)
IMPLIED_EXACT_UP, IMPLIED_EXACT_DOWN = 0.02, 0.005
CONVENTIONAL = frozenset({2, 3, 4, 5, 8, 10, 15, 20, 25, 30, 40, 50, 100, 200, 250, 500, 1000, 2000, 5000, 10000,
                          100000, 1000000})  # fmt: skip
IMPLIED_MAX_GAP_DAYS = 30  # consecutive sessions further apart are not compared (a suspension may hide a real move)
IMPLIED_FROM = date(1994, 7, 1)  # the Real: before it, currency resets and hyperinflation quotes make moves noise
IMPLIED_NEAR_DAYS = 45  # a candidate this close to a known stock event of the line is that event, not another


def implied_ipe_events(zones: Zones, prices: pl.LazyFrame, fac: pl.DataFrame, taken: pl.DataFrame) -> pl.DataFrame:
    """Stock events no source lists and Yahoo cannot show (lines delisted before Yahoo's coverage: TOYB3 2015,
    OGXP3 2016, BRPR3 2023): a one-day move of B3's raw close in BRL of at least `IMPLIED_IPE_MIN`x that our factors
    leave in place. It is kept when a CVM IPE filing of the issuer announces the regrouping, split or bonus around it
    (`ipe_evidence`), or when the move is 10x or more at a conventional ratio (`CONVENTIONAL`), from `IMPLIED_FROM`.
    The ratio is that fraction; the ex-date is the day of the move. `taken`: (instrument_id, ex_date) of the events
    already found."""
    brl = pl.col("brl_num").cast(pl.Float64) / pl.col("brl_den").cast(pl.Float64)
    day = (
        prices.filter(pl.col("market_segment") == "lote_padrao")
        .select("instrument_id", "trade_date", (pl.col("close").cast(pl.Float64) * brl).alias("c"))
        .filter(pl.col("c") > 0)
        .sort("instrument_id", "trade_date")
        .with_columns(
            (pl.col("c") / pl.col("c").shift(1)).over("instrument_id").log().alias("lr"),
            pl.col("trade_date").shift(1).over("instrument_id").alias("d0"),
        )
        .filter(
            (pl.col("trade_date") >= IMPLIED_FROM)
            & (pl.col("lr").abs() >= math.log(IMPLIED_IPE_MIN))
            & ((pl.col("trade_date") - pl.col("d0")).dt.total_days() <= IMPLIED_MAX_GAP_DAYS)
        )
        .collect()
        .join(fac.select("instrument_id", pl.col("ex_date").alias("trade_date"), "split_factor"),
              on=["instrument_id", "trade_date"], how="left")
        .filter(pl.col("split_factor").fill_null(1.0) == 1.0)
    )  # fmt: skip
    if taken.height:  # within IMPLIED_NEAR_DAYS of a known stock event: that event (B3's date may lag the move)
        near = (
            day.select("instrument_id", "trade_date")
            .join(taken.select("instrument_id", pl.col("ex_date").alias("_k")), on="instrument_id")
            .filter((pl.col("trade_date") - pl.col("_k")).dt.total_days().abs() <= IMPLIED_NEAR_DAYS)
            .select("instrument_id", "trade_date")
            .unique()
        )
        day = day.join(near, on=["instrument_id", "trade_date"], how="anti")
    rows = []
    for r in day.iter_rows(named=True):
        s = math.exp(-r["lr"])  # new shares per old that the move implies
        snapped = _snap(s)
        if snapped is None:
            continue
        num, den = snapped
        check = s / (num / den)
        kind = "REVERSE_SPLIT" if num < den else ("BONUS" if num / den < 2 else "SPLIT")
        rows.append({
            "instrument_id": r["instrument_id"], "event_type": kind,
            "data_com": r["d0"], "ex_date": r["trade_date"], "ratio_num": num, "ratio_den": den,
            "sources": "b3_cotahist", "price_check": check,
            "_exact": max(num, den) in CONVENTIONAL and min(num, den) == 1 and max(s, 1 / s) >= 10
            and abs(check - 1) <= (IMPLIED_EXACT_UP if num < den else IMPLIED_EXACT_DOWN),
        })  # fmt: skip
    if not rows:
        return pl.DataFrame()
    ev = ipe_evidence(zones, pl.DataFrame(rows))
    ev = ev.filter(pl.col("sources").str.contains("cvm_ipe") | pl.col("_exact")).drop("_exact")
    return ev.with_columns(pl.lit("confirmed").alias("status"), pl.col("ex_date").alias("ex_date_reported"))


CLUSTER_DAYS = 10  # applied stock events of a line this close together are checked as one move
CLUSTER_OFF = math.log(1.5)  # the full set must miss the move by more than 1.5x...
CLUSTER_FIT = 0.3  # ...and a subset must fit it within this (log) for the others to be rejected


def resolve_clusters(events: pl.DataFrame, prices: pl.LazyFrame) -> pl.DataFrame:
    """Several applied stock events of one line within `CLUSTER_DAYS` are graded one by one, so near-duplicates from
    different sources each agree with the same price move and all apply (BSLI3 2021-01-05: SPLIT 10:1 and 9:1;
    MNDL3 2011: 6:1 and 38:9; TUPY4 2010: a 1:1000 regrouping and a 1:1000 quote-basis change). Here the cluster
    is checked as one: when the product of its price factors misses the move from the last close before it to the
    first close after it by more than `CLUSTER_OFF`, the subset that fits the move within `CLUSTER_FIT` (fewest
    events, then closest) stays and the others become `conflicting` (not applied)."""
    from itertools import combinations

    stock = ["SPLIT", "REVERSE_SPLIT", "BONUS", "QUOTE_BASIS"]
    cand = events.with_row_index("_r").filter(
        pl.col("event_type").is_in(stock) & pl.col("status").is_in(list(APPLIED)) & pl.col("ratio_num").is_not_null()
    )
    if not cand.height:
        return events
    gap = (pl.col("ex_date") - pl.col("ex_date").shift(1)).dt.total_days().over("instrument_id")
    cand = cand.sort("instrument_id", "ex_date").with_columns(
        (gap > CLUSTER_DAYS).fill_null(True).cast(pl.Int32).cum_sum().over("instrument_id").alias("_cl")
    )
    multi = cand.filter(pl.len().over("instrument_id", "_cl") > 1)
    if not multi.height:
        return events
    brl = pl.col("brl_num").cast(pl.Float64) / pl.col("brl_den").cast(pl.Float64)
    px = (
        prices.filter(
            (pl.col("market_segment") == "lote_padrao")
            & pl.col("instrument_id").is_in(multi["instrument_id"].unique().implode())
        )
        .select("instrument_id", "trade_date", (pl.col("close").cast(pl.Float64) * brl).alias("c"))
        .collect()
    )

    def expect(sub: tuple[tuple[int, int, int], ...] | list[tuple[int, int, int]]) -> float:
        return sum(math.log(den / num) for _, num, den in sub)

    drop: list[int] = []
    for (iid, _), g in multi.group_by("instrument_id", "_cl"):
        first, last = g["ex_date"].min(), g["ex_date"].max()
        p = px.filter(pl.col("instrument_id") == iid)
        before = p.filter(pl.col("trade_date") < first).sort("trade_date").tail(1)["c"]
        after = p.filter(pl.col("trade_date") >= last).sort("trade_date").head(1)["c"]
        if not before.len() or not after.len() or before[0] <= 0 or after[0] <= 0:
            continue
        move = math.log(after[0] / before[0])
        rows = [(int(r), int(n), int(d)) for r, n, d in g.select("_r", "ratio_num", "ratio_den").iter_rows()]
        if abs(move - expect(rows)) <= CLUSTER_OFF:
            continue
        best: tuple[float, tuple[tuple[int, int, int], ...]] | None = None
        for k in range(1, len(rows)):
            for sub in combinations(rows, k):
                miss = abs(move - expect(sub))
                if miss <= CLUSTER_FIT and (best is None or miss < best[0]):
                    best = (miss, sub)
            if best is not None:
                break
        if best is not None:
            keep = {r for r, _, _ in best[1]}
            drop += [r for r, _, _ in rows if r not in keep]
    if not drop:
        return events
    status = pl.when(pl.col("_r").is_in(drop)).then(pl.lit("conflicting")).otherwise(pl.col("status"))
    return events.with_row_index("_r").with_columns(status.alias("status")).drop("_r")


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
        f = f.unique(["isin", "kind", "base_date", "value_per_quota", "payment_date"])
        by_isin = f.join(isin, on="isin", how="inner")
        # a notice whose ISIN is malformed ("0", "-", "TGARCTF009") is matched through its trading code, on the
        # ticker valid at the data-com (fundosnet.DISTRIBUTION)
        ticker = ids.filter(pl.col("scheme") == "TICKER").select(
            "instrument_id", pl.col("value").alias("trading_code"), "vt_from", "vt_to"
        )
        by_code = (
            f.join(isin.select("isin"), on="isin", how="anti")
            .join(ticker, on="trading_code", how="inner")
            .filter(pl.col("base_date").is_between(pl.col("vt_from"), pl.col("vt_to") + pl.duration(days=30)))
            .drop("vt_from", "vt_to")
            .unique(["isin", "trading_code", "kind", "base_date", "value_per_quota", "payment_date"])
        )
        f = pl.concat([by_isin, by_code.select(by_isin.columns)])
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


CASH_WORDS = "dividend|juros sobre|jscp|jcp|provento|rendimento|remunera"
CASH_DOC_DAYS = 60  # an announcing filing up to this many days before the ex-date
CASH_GAP_DAYS = 120  # Yahoo fills only where we hold no cash event of the line within this many days


def yahoo_cash_events(zones: Zones, events: pl.DataFrame, fac: pl.DataFrame, dates: pl.Series) -> pl.DataFrame:
    """Cash payouts B3's history lacks (Fras-le after 2002, B3's backend; ADR-0016 addendum): a Yahoo dividend with
    no cash event of ours within 120 days, proven by a CVM IPE filing of the issuer (Aviso aos Acionistas, Fato
    Relevante, Comunicado ao Mercado) whose subject names a payout, delivered up to 60 days before the ex-date. Yahoo
    states amounts on today's split basis, so the raw amount is Yahoo's divided by the product of our later split
    factors. Yahoo does not separate dividends from JCP: the type is OTHER_CASH. Status `confirmed` (two sources,
    one official); Yahoo alone is never applied."""
    y = _staging(zones, "yahoo_chart", "dividend")
    docs = _staging(zones, "cvm_ipe", "document")
    link = zones.core / "issuer_instrument" / "issuer_instrument.parquet"
    issuer = zones.core / "issuer" / "issuer.parquet"
    if y is None or docs is None or not link.exists() or not issuer.exists():
        return pl.DataFrame()
    ids = (
        _ids(zones)
        .filter(pl.col("scheme") == "TICKER")
        .select("instrument_id", pl.col("value").alias("ticker"), "vt_from", "vt_to")
    )
    y = (
        y.unique(["ticker", "ex_date", "amount"])
        .join(ids, on="ticker")
        .filter(pl.col("ex_date").is_between(pl.col("vt_from"), pl.col("vt_to") + pl.duration(days=10)))
        .select("instrument_id", "ticker", "ex_date", "amount")
    )
    have = events.filter(pl.col("cash_per_share").is_not_null()).select("instrument_id", pl.col("ex_date").alias("_e"))
    near = (
        y.join(have, on="instrument_id")
        # only where B3's history is silent around it: with B3 payouts nearby, a Yahoo-only date is Yahoo's error
        # (ITUB4 2025-03-18, the bonus day), never a payout to add
        .filter((pl.col("_e") - pl.col("ex_date")).dt.total_days().abs() <= CASH_GAP_DAYS)
        .select("instrument_id", "ex_date")
        .unique()
    )
    y = y.join(near, on=["instrument_id", "ex_date"], how="anti")
    if not y.height:
        return pl.DataFrame()
    cnpj = (
        pl.read_parquet(link)
        .join(pl.read_parquet(issuer).select("issuer_id", "cnpj"), on="issuer_id")
        .select("instrument_id", "cnpj")
        .unique("instrument_id")
    )
    text = (pl.col("subject").fill_null("") + " " + pl.col("doc_type").fill_null("")).str.to_lowercase()
    d = (
        docs.filter(pl.col("category").is_in(IPE_CATEGORIES))
        .select(
            pl.col("cnpj").str.replace_all(r"\D", "").alias("cnpj"),
            "delivered_on",
            pl.col("protocol").alias("ipe_protocol"),
            pl.col("link").alias("ipe_link"),
            text.alias("_t"),
        )
        .filter(pl.col("_t").str.contains(CASH_WORDS))
    )
    proof = (
        y.join(cnpj, on="instrument_id")
        .join(d, on="cnpj")
        .filter(
            pl.col("delivered_on").is_between(pl.col("ex_date").dt.offset_by(f"-{CASH_DOC_DAYS}d"), pl.col("ex_date"))
        )
        .sort("delivered_on", descending=True)
        .unique(["instrument_id", "ex_date", "amount"], keep="first")
        .select(
            "instrument_id", "ex_date", "amount", "ipe_protocol", "ipe_link",
            pl.col("delivered_on").alias("ipe_delivered_on"),
        )
    )  # fmt: skip
    if not proof.height:
        return pl.DataFrame()
    later = (
        proof.select("instrument_id", "ex_date")
        .unique()
        .join(
            fac.select("instrument_id", pl.col("ex_date").alias("_f"), "split_factor"), on="instrument_id", how="left"
        )
        .filter(pl.col("_f").is_null() | (pl.col("_f") > pl.col("ex_date")))
        .group_by("instrument_id", "ex_date")
        .agg(pl.col("split_factor").fill_null(1.0).log().sum().exp().alias("_k"))
    )
    out = proof.join(later, on=["instrument_id", "ex_date"], how="left").with_columns(pl.col("_k").fill_null(1.0))
    prev = pl.Series(dates).sort()
    data_com = [prev.filter(prev < e).max() for e in out["ex_date"].to_list()]
    return out.with_columns(
        pl.Series("data_com", data_com, dtype=pl.Date),
        pl.lit("OTHER_CASH").alias("event_type"),
        (pl.col("amount").cast(pl.Float64) / pl.col("_k")).round(8).cast(CASH).alias("cash_per_share"),
        pl.lit("yahoo_chart,cvm_ipe").alias("sources"),
        pl.lit("confirmed").alias("status"),
    ).drop("amount", "_k")


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
        | pl.col("status").is_in(APPLIED)
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


SPINOFF_LABELS = ("CIS RED CAP",)  # B3: spin-off with capital reduction; factor = new shares per 100 held
SPINOFF_SESSIONS = 10  # the spun-off line must trade within this many sessions of the ex-date


def spinoff_factors(zones: Zones, prices: pl.LazyFrame, dates: pl.Series) -> pl.DataFrame:
    """Price factor of the parent at a spin-off (B3 `CIS RED CAP` whose issued asset is another ISIN): holders
    receive `factor`/100 shares of the new line per share (PCAR3 -> ASAI3 2021: 100, 1 for 1; SANB -> GETT 2021: 25).
    f = 1 - k x close(new line, first session from the ex-date) / close(parent, data-com), kept when 0 < f < 1. The
    value moves to the new line, so the parent's earlier prices are scaled by f, as a split would be."""
    s = _staging(zones, "b3_company_events", "stock_event")
    empty = pl.DataFrame(schema={"instrument_id": pl.String, "ex_date": pl.Date, "spin_factor": pl.Float64})
    if s is None:
        return empty
    ids = _ids(zones).filter(pl.col("scheme") == "ISIN").select("instrument_id", pl.col("value").alias("isin"))
    ids = ids.unique("isin")
    s = (
        s.filter(
            pl.col("label").is_in(SPINOFF_LABELS)
            & pl.col("asset_issued").is_not_null()
            & (pl.col("asset_issued") != pl.col("isin"))
            & pl.col("last_date_prior").is_not_null()
        )
        .unique(["isin", "asset_issued", "factor", "last_date_prior"])
        .join(ids, on="isin")
        .join(ids.rename({"instrument_id": "to_id", "isin": "asset_issued"}), on="asset_issued")
        .with_columns(pl.col("last_date_prior").alias("_com"))
    )
    if not s.height:
        return empty
    s = s.with_columns(next_session(dates, s["_com"]).alias("ex_date"))
    brl = pl.col("brl_num").cast(pl.Float64) / pl.col("brl_den").cast(pl.Float64)
    closes = (
        prices.filter(pl.col("market_segment") == "lote_padrao")
        .select("instrument_id", "trade_date", (pl.col("close").cast(pl.Float64) * brl).alias("c"))
        .collect()
        .sort("instrument_id", "trade_date")
    )
    cum = s.sort("instrument_id", "_com").join_asof(
        closes.rename({"trade_date": "_com", "c": "_pa"}), on="_com", by="instrument_id", strategy="backward",
        check_sortedness=False,
    )  # fmt: skip
    first = cum.with_columns(pl.col("ex_date").alias("_t")).sort("to_id", "_t").join_asof(
        closes.rename({"instrument_id": "to_id", "trade_date": "_t", "c": "_pb"}).with_columns(
            pl.col("_t").alias("_tb")
        ),
        on="_t", by="to_id", strategy="forward", check_sortedness=False,
    )  # fmt: skip
    k = pl.col("factor").cast(pl.Float64) / 100
    within = pl.col("_tb").is_not_null() & (
        (pl.col("_tb") - pl.col("ex_date")).dt.total_days() <= SPINOFF_SESSIONS * 2  # calendar days, ~10 sessions
    )
    f = first.filter(within & (pl.col("_pa") > 0)).with_columns((1 - k * pl.col("_pb") / pl.col("_pa")).alias("f"))
    f = f.filter((pl.col("f") > 0) & (pl.col("f") < 1))
    return f.group_by("instrument_id", "ex_date").agg(pl.col("f").product().alias("spin_factor"))


def with_spinoffs(fac: pl.DataFrame, spin: pl.DataFrame) -> pl.DataFrame:
    if not spin.height:
        return fac
    out = fac.join(spin, on=["instrument_id", "ex_date"], how="full", coalesce=True)
    return out.with_columns(
        (pl.col("split_factor").fill_null(1.0) * pl.col("spin_factor").fill_null(1.0)).alias("split_factor"),
        pl.col("cash_factor").fill_null(1.0),
    ).select(FACTOR.names)


def build(zones: Zones, run: IngestRun | None = None) -> dict[str, int]:
    if not (zones.core / "price_daily").exists():
        return {}
    dates = sessions(zones)
    prices = pl.scan_parquet(zones.core / "price_daily" / "*.parquet")
    stock = stock_events(zones, dates)
    if stock.height:
        stock = redate(price_check(stock, prices, ipca_level(zones)), prices)
        stock = ipe_evidence(zones, stock)
        stock = stock.with_columns(
            status(pl.col("sources"), pl.col("_move"), pl.col("_net"), pl.col("_priced")).alias("status")
        ).drop("_g", "_net", "_move", "_priced")
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
    basis = quote_basis_events(prices, stock)
    cols = [c for c in EVENT.names if c != "event_id"]
    schema = EVENT.schema()

    def fill(f: pl.DataFrame) -> pl.DataFrame:
        return f.with_columns([pl.lit(None, dtype=schema[c]).alias(c) for c in cols if c not in f.columns]).select(cols)

    parts = [fill(f) for f in (stock, cash, rights, basis) if f.height]

    def assemble(parts: list[pl.DataFrame]) -> pl.DataFrame:
        allev = pl.concat(parts, how="vertical_relaxed").filter(pl.col("ex_date").is_not_null())
        allev = allev.sort("instrument_id", "ex_date", "event_type", "sources")
        return allev.with_columns(
            (
                pl.col("instrument_id") + "|" + pl.col("event_type") + "|" + pl.col("ex_date").cast(pl.String) + "|"
                + pl.int_range(pl.len()).over("instrument_id", "event_type", "ex_date").cast(pl.String)
            ).alias("event_id")
        ).select(EVENT.names)  # fmt: skip

    allev = assemble(parts)
    # pass 2: events only the official prices and Yahoo show, found against the factors of pass 1
    spin = spinoff_factors(zones, prices, dates)
    fac0 = with_spinoffs(factors(EVENT.split(allev)[0], prices), spin)
    write_parquet(
        fac0.sort("instrument_id", "ex_date"), zones.derived / "adjustment_factor" / "adjustment_factor.parquet"
    )
    implied = implied_events(zones, prices, fac0)
    # pass 2b: the same misses on lines Yahoo does not cover, proven by a CVM filing or by an exact ratio
    # any stock event already known (applied or not) blocks a candidate near it: B3's date and the day prices move
    # can differ by days (CBEE3 1:40000 reported 2016-01-15, first trade after it 01-29)
    known = allev.filter(pl.col("event_type").is_in(["SPLIT", "REVERSE_SPLIT", "BONUS", "QUOTE_BASIS"]))
    known = known.select("instrument_id", "ex_date")
    taken = pl.concat([known, implied.select("instrument_id", "ex_date")]) if implied.height else known
    more = implied_ipe_events(zones, prices, fac0, taken)
    if more.height:
        implied = pl.concat([implied, more], how="diagonal_relaxed") if implied.height else more
    if implied.height:
        allev = assemble([*parts, fill(implied)])
    good, bad = EVENT.split(allev)
    # pass 3: payouts B3's history lacks, from Yahoo proven by a CVM filing (needs the split factors of pass 2)
    extra = yahoo_cash_events(zones, good, with_spinoffs(factors(good, prices), spin), dates)
    if extra.height:
        allev = assemble([*parts, *([fill(implied)] if implied.height else []), fill(extra)])
        good, bad = EVENT.split(allev)
    good = resolve_clusters(good, prices)
    write_parquet(good, zones.core / "corporate_event" / "corporate_event.parquet")
    q = zones.quarantine / "core" / "corporate_event.parquet"
    if bad.height:
        write_parquet(bad, q)
    else:
        q.unlink(missing_ok=True)
    fac = with_spinoffs(factors(good, prices), spin)
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
