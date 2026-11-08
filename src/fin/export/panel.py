"""Model-ready panels (`fin export panel`): the data layer as two tidy monthly tables any model can read.

- `equity_monthly.parquet`: one row per (B3 share or unit, month) with a standard-lot session in the month: delisted
  lines included (point-in-time universe, no survivorship). Returns come from raw closes and the derived adjustment
  factors (invariant 6); fundamentals come from `valuation(d)` at each month end, i.e. as known on that date
  (versions delivered later, restatements included, are not seen before their delivery: ADR-0021, ADR-0027).
- `macro_monthly.parquet`: one row per month with Brazilian and US context series (month-end or month values).
- `README.md`: every column with its meaning and unit.

Characteristics use only data up to the month end they are dated by. Returns of month t are the target a model
would predict from characteristics of month t-1: shift them yourself; nothing here is shifted.
"""

from __future__ import annotations

import math
from datetime import date
from pathlib import Path

import duckdb
import polars as pl

from fin.config import Zones

START = date(2010, 1, 1)
SUSPECT = 4.0  # a month's total return beyond 4x (or 1/4) is flagged: 57 of 82,227 months (2026-11-08), mostly
# share-basis changes no source reports (TELB4 2011, KROT3 2012 unit conversion)

EQUITY_COLUMNS: dict[str, tuple[str, str]] = {
    "month": ("first day of the month", "date"),
    "month_end": ("last B3 session of the month (market-wide)", "date"),
    "instrument_id": ("LASTRO instrument (ISIN-based identity)", ""),
    "ticker": ("ticker of the line's last session in the month", ""),
    "issuer_id": ("issuer (CNPJ-based); null when no link", ""),
    "issuer_name": ("issuer name", ""),
    "sector": ("CVM sector of the issuer", ""),
    "link_method": (
        "how the line is tied to its issuer (b3_root, fca_ticker, isin_issuer, b3_isin_emitter, name_history)",
        "",
    ),
    "last_session": ("the line's last session in the month", "date"),
    "days_stale": ("calendar days between last_session and month_end", "days"),
    "sessions": ("standard-lot sessions in the month", "count"),
    "volume_brl": ("traded volume in the month", "BRL"),
    "avg_daily_volume_brl": ("mean volume per session in the month", "BRL"),
    "close_brl": ("raw close at last_session", "BRL per share"),
    "ret_total": ("total return of the month (dividends reinvested, splits adjusted)", "ratio"),
    "ret_price": ("price return of the month (splits adjusted, no dividends)", "ratio"),
    "ret_suspect": (
        "total return beyond 4x up or down in a month: likely an unadjusted event (filter before modelling)",
        "flag",
    ),
    "mom_12_1": ("compounded total return from month t-12 to t-2 (11 months)", "ratio"),
    "vol_12m": ("annualised standard deviation of the last 12 monthly total returns", "ratio per year"),
    "dy_12m": ("trailing 12-month dividend yield: total-return growth / price-return growth - 1", "ratio"),
    "market_cap_brl": ("issuer market cap at month_end, as known then (shares x closes; ADR-0021)", "BRL"),
    "price_earnings": ("issuer market cap / trailing 12-month controlling earnings, as known then", "ratio"),
    "price_book": ("issuer market cap / controlling equity, as known then", "ratio"),
    "earnings_ttm_brl": ("trailing 12-month controlling earnings, as known then", "BRL"),
    "book_value_brl": ("controlling equity of the latest balance sheet, as known then", "BRL"),
}
MACRO: dict[str, tuple[str, str, str, str]] = {
    # column: (series_id, how, meaning, unit)
    "cdi_month_pct": ("bcb_sgs:4391", "value", "CDI accumulated in the month", "% a.m."),
    "selic_month_pct": ("bcb_sgs:4390", "value", "Selic accumulated in the month", "% a.m."),
    "selic_target_pct_aa": ("bcb_sgs:432", "last", "Selic target at month end", "% a.a."),
    "ipca_month_pct": ("bcb_sgs:433", "value", "IPCA, monthly change", "% m/m"),
    "igpm_month_pct": ("bcb_sgs:189", "value", "IGP-M, monthly change", "% m/m"),
    "ibc_br_sa": ("bcb_sgs:24364", "value", "IBC-Br activity index, seasonally adjusted", "index"),
    "ibovespa": ("ipeadata:GM366_IBVSP366", "last", "Ibovespa level at month end", "points"),
    "usd_brl_ptax": ("bcb_ptax:USD:sell", "last", "PTAX USD/BRL selling rate at month end", "BRL per USD"),
    "fed_funds_pct": ("fred:DFF", "mean", "effective Fed funds rate, month mean", "% a.a."),
    "us10y_pct": ("us_treasury:par/10Y", "last", "US Treasury 10-year par yield at month end", "% a.a."),
}

EQUITY_SQL = """
WITH eq AS (SELECT instrument_id FROM instrument WHERE asset_class IN ('share', 'unit')),
me AS (
    SELECT date_trunc('month', trade_date)::DATE AS month, max(trade_date) AS month_end
    FROM price_daily WHERE market_segment = 'lote_padrao' AND trade_date >= $start GROUP BY 1
),
px AS (
    SELECT p.instrument_id, date_trunc('month', p.trade_date)::DATE AS month,
           arg_max(p.ticker, p.trade_date) AS ticker, max(p.trade_date) AS last_session, count(*) AS sessions,
           sum(CAST(p.volume AS DOUBLE)) AS volume_brl,
           arg_max(CAST(p.close AS DOUBLE) * p.brl_num / p.brl_den, p.trade_date) AS close_brl
    FROM price_daily p JOIN eq USING (instrument_id)
    WHERE p.market_segment = 'lote_padrao' AND p.trade_date >= $start - INTERVAL 13 MONTH
    GROUP BY 1, 2
),
adj AS (  -- factors of the events after the close: close x factor is the close in today's basis
    SELECT px.*, exp(coalesce(sum(ln(f.split_factor * f.cash_factor)), 0)) AS f_total,
                 exp(coalesce(sum(ln(f.split_factor)), 0)) AS f_split
    FROM px LEFT JOIN adjustment_factor f ON f.instrument_id = px.instrument_id AND f.ex_date > px.last_session
    GROUP BY ALL
),
r AS (
    SELECT *,
        CASE WHEN date_diff('month', lag(month) OVER w, month) = 1
             THEN close_brl * f_total / (lag(close_brl) OVER w * lag(f_total) OVER w) - 1 END AS ret_total,
        CASE WHEN date_diff('month', lag(month) OVER w, month) = 1
             THEN close_brl * f_split / (lag(close_brl) OVER w * lag(f_split) OVER w) - 1 END AS ret_price
    FROM adj WINDOW w AS (PARTITION BY instrument_id ORDER BY month)
),
c AS (
    SELECT *,
        CASE WHEN count(ret_total) OVER m11 = 11 THEN exp(sum(ln(1 + ret_total)) OVER m11) - 1 END AS mom_12_1,
        CASE WHEN count(ret_total) OVER m12 = 12 THEN stddev_samp(ret_total) OVER m12 * sqrt(12) END AS vol_12m,
        CASE WHEN count(ret_total) OVER m12 = 12
             THEN exp(sum(ln(1 + ret_total)) OVER m12 - sum(ln(1 + ret_price)) OVER m12) - 1 END AS dy_12m
    FROM r
    WINDOW m11 AS (PARTITION BY instrument_id ORDER BY month ROWS BETWEEN 12 PRECEDING AND 2 PRECEDING),
           m12 AS (PARTITION BY instrument_id ORDER BY month ROWS BETWEEN 11 PRECEDING AND CURRENT ROW)
),
link AS (
    SELECT ii.instrument_id, any_value(ii.issuer_id) AS issuer_id, any_value(ii.method) AS link_method
    FROM issuer_instrument ii GROUP BY 1
)
SELECT c.month, me.month_end, c.instrument_id, c.ticker, link.issuer_id,
       coalesce(i.trade_name, i.legal_name) AS issuer_name, i.sector, link.link_method, c.last_session,
       date_diff('day', c.last_session, me.month_end) AS days_stale, c.sessions, c.volume_brl,
       c.volume_brl / c.sessions AS avg_daily_volume_brl, c.close_brl, c.ret_total, c.ret_price, c.mom_12_1,
       c.vol_12m, c.dy_12m
FROM c JOIN me USING (month)
LEFT JOIN link USING (instrument_id)
LEFT JOIN issuer i ON i.issuer_id = link.issuer_id
ORDER BY c.month, c.instrument_id
"""


def _connect(zones: Zones) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(zones.catalog), read_only=True, config={"max_temp_directory_size": "4GB"})


def equity_monthly(con: duckdb.DuckDBPyConnection, start: date = START) -> pl.DataFrame:
    cur = con.execute(EQUITY_SQL.replace("$start", f"DATE '{start.isoformat()}'"))
    df = pl.DataFrame(
        cur.fetchall(), schema=[d[0] for d in cur.description or []], orient="row", infer_schema_length=None
    )
    ends = df.select("month_end").unique().sort("month_end")["month_end"].to_list()
    vals: list[pl.DataFrame] = []
    try:
        for d in ends:  # fundamentals as known at each month end (0.4 s per date with the derived metrics)
            cur = con.execute(
                "SELECT ?::DATE AS month_end, issuer_id, market_cap_brl, price_earnings, price_book, "
                "earnings_ttm AS earnings_ttm_brl, book_value AS book_value_brl FROM valuation(?)",
                [d, d],
            )
            vals.append(pl.DataFrame(cur.fetchall(), schema=[x[0] for x in cur.description or []], orient="row"))
    except duckdb.CatalogException:  # no valuation macro (no fundamentals in this catalog)
        vals = []
    if vals:
        v = pl.concat([x for x in vals if x.height], how="vertical_relaxed")
        df = df.join(v, on=["month_end", "issuer_id"], how="left")
    else:
        fund = ("market_cap_brl", "price_earnings", "price_book", "earnings_ttm_brl", "book_value_brl")
        df = df.with_columns(*[pl.lit(None, dtype=pl.Float64).alias(c) for c in fund])
    big = (1 + pl.col("ret_total")).log().abs() > math.log(SUSPECT)
    return df.with_columns(big.fill_null(False).alias("ret_suspect")).select(list(EQUITY_COLUMNS))


def macro_monthly(con: duckdb.DuckDBPyConnection, start: date = START) -> pl.DataFrame:
    frames: list[pl.DataFrame] = []
    for col, (sid, how, _, _) in MACRO.items():
        agg = {"value": "any_value(v)", "last": "arg_max(v, vt_start)", "mean": "avg(v)"}[how]
        try:
            cur = con.execute(
                f"SELECT date_trunc('month', vt_start)::DATE AS month, {agg} AS {col} FROM ("
                "  SELECT vt_start, CAST(value AS DOUBLE) AS v FROM series_observation"
                "  WHERE series_id = ? AND vt_start >= ?"
                "  QUALIFY row_number() OVER (PARTITION BY vt_start ORDER BY version DESC) = 1"
                ") GROUP BY 1",
                [sid, start],
            )
        except duckdb.CatalogException:
            continue
        frames.append(pl.DataFrame(cur.fetchall(), schema={"month": pl.Date, col: pl.Float64}, orient="row"))
    if not frames:
        return pl.DataFrame(schema={"month": pl.Date})
    out = frames[0]
    for f in frames[1:]:
        out = out.join(f, on="month", how="full", coalesce=True)
    return out.sort("month")


def _readme(eq: pl.DataFrame, macro: pl.DataFrame) -> str:
    lines = [
        "# LASTRO model panels",
        "",
        f"Built from the catalog. Equity: {eq.height:,} rows, {eq['instrument_id'].n_unique():,} lines, "
        f"{eq['month'].min()} to {eq['month'].max()}. Macro: {macro.height} months.",
        "",
        "Characteristics of month t use data up to its month end only; fundamentals are as known then. Returns of",
        "month t are realised in month t: to predict, use characteristics of t-1 (shift yourself).",
        "",
        "## equity_monthly.parquet",
        "",
        "| column | meaning | unit |",
        "|---|---|---|",
        *[f"| `{k}` | {m} | {u} |" for k, (m, u) in EQUITY_COLUMNS.items()],
        "",
        "## macro_monthly.parquet",
        "",
        "| column | series | meaning | unit |",
        "|---|---|---|---|",
        "| `month` | — | first day of the month | date |",
        *[f"| `{k}` | `{s}` ({h}) | {m} | {u} |" for k, (s, h, m, u) in MACRO.items()],
        "",
    ]
    return "\n".join(lines)


def build(zones: Zones, start: date = START) -> Path:
    out = zones.exports / "panel"
    out.mkdir(parents=True, exist_ok=True)
    con = _connect(zones)
    try:
        eq = equity_monthly(con, start)
        macro = macro_monthly(con, start)
    finally:
        con.close()
    eq.write_parquet(out / "equity_monthly.parquet")
    macro.write_parquet(out / "macro_monthly.parquet")
    (out / "README.md").write_text(_readme(eq, macro), encoding="utf-8")
    return out
