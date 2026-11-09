"""Near-duplicate stock events from different sources: the cluster is checked against the one price move."""

from __future__ import annotations

from datetime import date

import polars as pl

from fin.core.events import repair_ratios, resolve_clusters


def _prices(closes: list[tuple[date, float]]) -> pl.LazyFrame:
    return pl.DataFrame(
        {"instrument_id": ["I"] * len(closes), "trade_date": [d for d, _ in closes], "close": [c for _, c in closes],
         "market_segment": ["lote_padrao"] * len(closes), "brl_num": [1] * len(closes), "brl_den": [1] * len(closes)}
    ).lazy()  # fmt: skip


def _events(rows: list[tuple[str, int, int, date]]) -> pl.DataFrame:
    t, n, d, x = zip(*rows, strict=True)
    return pl.DataFrame({"instrument_id": ["I"] * len(rows), "event_type": list(t), "ratio_num": list(n),
                         "ratio_den": list(d), "ex_date": list(x), "status": ["confirmed"] * len(rows)})  # fmt: skip


def test_two_splits_where_the_price_shows_one() -> None:
    px = _prices([(date(2021, 1, 4), 40.0), (date(2021, 1, 5), 4.1)])  # one 10:1 split (BSLI3 2021-01-05)
    ev = _events([("SPLIT", 10, 1, date(2021, 1, 5)), ("SPLIT", 9, 1, date(2021, 1, 5))])
    out = resolve_clusters(ev, px)
    assert out["status"].to_list() == ["confirmed", "conflicting"]


def test_a_cluster_that_fits_the_move_is_left_alone() -> None:
    px = _prices([(date(2021, 1, 4), 40.0), (date(2021, 1, 12), 1.0)])  # 10:1 then 4:1 within the window: 40x
    ev = _events([("SPLIT", 10, 1, date(2021, 1, 5)), ("SPLIT", 4, 1, date(2021, 1, 12))])
    assert resolve_clusters(ev, px)["status"].to_list() == ["confirmed", "confirmed"]


def _one(sources: str, pc: float) -> pl.DataFrame:
    return pl.DataFrame({"event_id": ["I|REVERSE_SPLIT|2011-01-24|0"], "instrument_id": ["I"],
                         "event_type": ["REVERSE_SPLIT"], "ratio_num": [1], "ratio_den": [10],
                         "ex_date": [date(2011, 1, 24)], "status": ["confirmed"], "sources": [sources],
                         "price_check": [pc]})  # fmt: skip


def test_filing_backed_ratio_that_misses_the_move_is_repaired() -> None:
    # TELB4 2011-01-24: Yahoo's 1:10, the filing's 10,000 into 1; the move is 9,546x
    out = repair_ratios(_one("yahoo_chart,cvm_ipe", 0.001048))
    assert out["status"].to_list() == ["conflicting", "confirmed"]
    fixed = out.row(1, named=True)
    assert (fixed["ratio_num"], fixed["ratio_den"], fixed["sources"]) == (1, 10000, "cvm_ipe,b3_cotahist")
    assert abs(fixed["price_check"] - 1.048) < 1e-9


def test_no_filing_or_no_conventional_fit_is_left_alone() -> None:
    assert repair_ratios(_one("yahoo_chart", 0.001048))["status"].to_list() == ["confirmed"]
    assert repair_ratios(_one("yahoo_chart,cvm_ipe", 0.0016))["status"].to_list() == ["confirmed"]  # 1:6,250
