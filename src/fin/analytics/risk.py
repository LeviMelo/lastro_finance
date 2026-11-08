"""Portfolio risk and exposure (PLAN §10 Stage K): measured on the portfolio's own buy-and-hold value path.
Tesouro Direto lines follow the morning sell PU (coupons excluded).

From `price_adjusted` (total-return closes, BRL of the day) the value of each line is quantity x close_adjusted
rescaled so that it starts at the line's start value; the portfolio value is their sum on the sessions all
lines share. On it:
- annualised volatility of daily log returns (x sqrt(252));
- maximum drawdown (the deepest fall from a running peak) and its dates;
- beta to the Ibovespa: covariance of daily log returns over the index's variance, on common dates;
- sector exposure: current weights grouped by the issuer's CVM sector (`issuer.sector`), "sem setor" when unknown.

These are descriptive statistics of the realised path, not forecasts.
"""

from __future__ import annotations

import math
from datetime import date

import duckdb
import polars as pl

TRADING_DAYS = 252


def value_path(con: duckdb.DuckDBPyConnection, holdings: pl.DataFrame, since: date, as_of: date) -> pl.DataFrame:
    """(trade_date, value_brl) of the buy-and-hold portfolio; `holdings` has instrument_id and quantity."""
    parts: list[pl.DataFrame] = []
    for r in holdings.filter(pl.col("instrument_id").is_not_null()).iter_rows(named=True):
        if r.get("asset_class") == "tesouro_direto":  # the morning sell PU path (coupons excluded, as in performance)
            sql = (
                "SELECT base_date, CAST(sell_pu AS DOUBLE), CAST(sell_pu AS DOUBLE) FROM tesouro_price_daily "
                "WHERE instrument_id = ? AND base_date BETWEEN ? AND ? AND sell_pu > 0 ORDER BY base_date"
            )
        else:
            sql = (
                "SELECT trade_date, close, close_adjusted FROM price_adjusted WHERE instrument_id = ? "
                "AND trade_date BETWEEN ? AND ? ORDER BY trade_date"
            )
        cur = con.execute(sql, [r["instrument_id"], since, as_of])
        rows = cur.fetchall()
        if not rows:
            continue
        df = pl.DataFrame(rows, schema=["trade_date", "close", "adj"], orient="row")
        start = float(r["quantity"]) * float(df["close"][0])
        parts.append(df.select("trade_date", (start * pl.col("adj") / df["adj"][0]).alias(str(r["instrument_id"]))))
    if not parts:
        return pl.DataFrame(schema={"trade_date": pl.Date, "value_brl": pl.Float64})
    wide = parts[0]
    for p in parts[1:]:
        wide = wide.join(p, on="trade_date", how="full", coalesce=True)
    wide = wide.sort("trade_date").fill_null(strategy="forward").drop_nulls()  # a line not yet traded: wait for it
    cols = [c for c in wide.columns if c != "trade_date"]
    return wide.select("trade_date", pl.sum_horizontal(cols).alias("value_brl"))


def stats(path: pl.DataFrame, index: pl.DataFrame | None = None) -> dict[str, float | date | None]:
    """Volatility, drawdown and beta of a value path; `index` has (trade_date, level)."""
    if path.height < 3:
        return {"volatility": None, "max_drawdown": None, "peak": None, "trough": None, "beta": None}
    p = path.with_columns((pl.col("value_brl") / pl.col("value_brl").shift(1)).log().alias("r"))
    vol = float(p.select(pl.col("r").drop_nulls().std()).item() or 0) * math.sqrt(TRADING_DAYS)
    dd = p.with_columns((pl.col("value_brl") / pl.col("value_brl").cum_max() - 1).alias("dd"))
    i = int(dd["dd"].arg_min() or 0)
    trough = dd["trade_date"][i]
    peak = dd.filter(pl.col("trade_date") <= trough).sort("value_brl")["trade_date"][-1]
    beta = None
    if index is not None and index.height > 2:
        ix = index.sort("trade_date").with_columns((pl.col("level") / pl.col("level").shift(1)).log().alias("ri"))
        j = p.join(ix.select("trade_date", "ri"), on="trade_date").drop_nulls(["r", "ri"])
        if j.height > 2:
            var = float(j.select(pl.col("ri").var()).item() or 0)
            cov = float(j.select(pl.cov("r", "ri")).item() or 0)
            beta = cov / var if var else None
    return {"volatility": vol, "max_drawdown": float(dd["dd"][i]), "peak": peak, "trough": trough, "beta": beta}


def sector_exposure(con: duckdb.DuckDBPyConnection, holdings: pl.DataFrame) -> pl.DataFrame:
    """Current weights by the issuer's CVM sector."""
    h = holdings.filter(pl.col("instrument_id").is_not_null() & pl.col("weight").is_not_null())
    if not h.height:
        return pl.DataFrame(schema={"sector": pl.String, "weight": pl.Float64})
    try:
        cur = con.execute(
            "SELECT ii.instrument_id, any_value(s.sector) FROM issuer_instrument ii JOIN issuer s USING (issuer_id) "
            "WHERE ii.instrument_id IN (SELECT unnest(?)) GROUP BY 1",
            [h["instrument_id"].to_list()],
        )
        sec = pl.DataFrame(cur.fetchall(), schema=["instrument_id", "sector"], orient="row")
    except duckdb.Error:  # no issuer tables (or no sector) in this catalog: every line is "sem setor"
        sec = pl.DataFrame(schema={"instrument_id": pl.String, "sector": pl.String})
    return (
        h.join(sec, on="instrument_id", how="left")
        .with_columns(pl.col("sector").fill_null("sem setor"))
        .group_by("sector")
        .agg(pl.col("weight").sum())
        .sort("weight", descending=True)
    )
