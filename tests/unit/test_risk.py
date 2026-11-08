"""Risk statistics of a value path: a known drawdown, zero volatility on a flat path, beta of a scaled index."""

from __future__ import annotations

import math
from datetime import date, timedelta

import polars as pl

from fin.analytics import risk
from fin.analytics.risk import stats


def _path(values: list[float]) -> pl.DataFrame:
    return pl.DataFrame({"trade_date": [date(2025, 1, 1) + timedelta(days=i) for i in range(len(values))],
                         "value_brl": values})  # fmt: skip


def test_drawdown_peak_and_trough() -> None:
    s = stats(_path([100, 120, 90, 110, 130]))
    assert abs(s["max_drawdown"] - (90 / 120 - 1)) < 1e-12  # type: ignore[operator]
    assert s["peak"] == date(2025, 1, 2) and s["trough"] == date(2025, 1, 3)


def test_flat_path_has_no_volatility_and_beta_of_twice_the_index_is_two() -> None:
    assert stats(_path([100.0] * 5))["volatility"] == 0
    ix = [100.0, 101.0, 99.5, 102.0, 101.0, 103.0]
    port = [100 * math.exp(2 * math.log(v / ix[0])) for v in ix]  # log returns exactly twice the index's
    idx = _path(ix).rename({"value_brl": "level"})
    assert abs(stats(_path(port), idx)["beta"] - 2.0) < 1e-9  # type: ignore[operator]


def test_value_path_follows_the_tesouro_sell_pu() -> None:
    import duckdb

    con = duckdb.connect()
    con.execute("CREATE TABLE tesouro_price_daily (instrument_id VARCHAR, base_date DATE, sell_pu DECIMAL(18,2))")
    con.execute("INSERT INTO tesouro_price_daily VALUES ('t1','2026-01-02',1000),('t1','2026-01-05',1010),"
                "('t1','2026-01-06',0)")  # fmt: skip
    h = pl.DataFrame({"instrument_id": ["t1"], "asset_class": ["tesouro_direto"], "quantity": [2.0]})
    p = risk.value_path(con, h, date(2026, 1, 1), date(2026, 1, 31))
    assert p["value_brl"].to_list() == [2000.0, 2020.0]  # a zero PU (no sale that day) is not a price
