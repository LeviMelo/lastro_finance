"""Risk statistics of a value path: a known drawdown, zero volatility on a flat path, beta of a scaled index."""

from __future__ import annotations

import math
from datetime import date, timedelta

import polars as pl

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
