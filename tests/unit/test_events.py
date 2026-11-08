"""Corporate-event rules: B3 factor semantics per label (golden_events.md), ex-date = next session, one event per
(instrument, ex-date, ratio) across sources, and the price test that confirms a stock event."""

from __future__ import annotations

from datetime import date
from fractions import Fraction

import polars as pl

from fin.core import events


def test_b3_factor_reads_by_label() -> None:
    # golden_events.md: ITUB 3 % = 103:100, SLCE 12.5 % = 9:8, RADL 2 % = 51:50, EGIE 40 % = 7:5, BHIA 0.04 = 1:25
    assert events.b3_ratio("BONIFICACAO", Fraction("3")) == Fraction(103, 100)
    assert events.b3_ratio("BONIFICACAO", Fraction("12.5")) == Fraction(9, 8)
    assert events.b3_ratio("BONIFICACAO", Fraction("2")) == Fraction(51, 50)
    assert events.b3_ratio("BONIFICACAO", Fraction("40")) == Fraction(7, 5)
    assert events.b3_ratio("GRUPAMENTO", Fraction("0.04")) == Fraction(1, 25)
    assert events.b3_ratio("DESDOBRAMENTO", Fraction("100")) == Fraction(2, 1)
    assert events.b3_ratio("INCORPORACAO", Fraction("50")) is None


def test_ex_date_is_the_next_session() -> None:
    sessions = pl.Series([date(2025, 12, 22), date(2025, 12, 23), date(2025, 12, 26), date(2026, 1, 2)])
    com = pl.Series([date(2025, 12, 23), date(2025, 12, 30), date(2025, 12, 22)])
    # ITUB data-com 23/12 -> ex 26/12; SLCE 30/12 -> ex 02/01; RADL 22/12 -> 23/12 (golden_events.md)
    assert events.next_session(sessions, com).to_list() == [date(2025, 12, 26), date(2026, 1, 2), date(2025, 12, 23)]


def test_sources_merge_on_instrument_date_and_ratio() -> None:
    d = date(2025, 12, 26)
    rows = [
        {"instrument_id": "I1", "event_type": "SPLIT", "data_com": None, "ex_date": d, "ratio": Fraction(103, 100),
         "approved_on": None, "source": "yahoo_chart"},
        {"instrument_id": "I1", "event_type": "BONUS", "data_com": date(2025, 12, 23), "ex_date": d,
         "ratio": Fraction(103, 100), "approved_on": date(2025, 12, 18), "source": "b3_company_events"},
        {"instrument_id": "I1", "event_type": "BONUS", "data_com": None, "ex_date": date(2025, 3, 18),
         "ratio": Fraction(11, 10), "approved_on": None, "source": "yahoo_chart"},
    ]  # fmt: skip
    out = events.merge_stock(rows).sort("ex_date")
    assert out.height == 2
    dec = out.row(1, named=True)
    assert dec["event_type"] == "BONUS" and dec["sources"] == "b3_company_events,yahoo_chart"
    assert (dec["ratio_num"], dec["ratio_den"], dec["data_com"]) == (103, 100, date(2025, 12, 23))


def test_price_test_accepts_the_ratio_and_rejects_a_wrong_one() -> None:
    df = pl.DataFrame(
        {"move": [2.0, 30.0 * 0.8, 1.0, 10.0, 1.05 * 0.973, 0.9], "net": [2.0, 30.0, 2.0, 100.0, 1.05, 1.05]}
    )
    out = df.select(events.agrees(pl.col("move"), pl.col("net")).alias("ok"))["ok"].to_list()
    # exact split; reverse split 1:30 with a 20 % fall after it; no move at all; a 1:100 that moved only 10x;
    # a 21:20 bonus inside the day's noise (RENT3 2019-12); a 21:20 bonus after which the price fell 10 %
    assert out == [True, True, False, False, True, False]


def test_status_needs_two_sources_or_the_price() -> None:
    df = pl.DataFrame(
        {
            "sources": ["b3_company_events,yahoo_chart", "b3_company_events", "yahoo_chart", "yahoo_chart"],
            "move": [None, 1.03, 2.0, 40.0],
            "net": [1.03, 1.03, 2.0, 100.0],
        }
    )
    out = df.select(events.status(pl.col("sources"), pl.col("move"), pl.col("net")).alias("s"))["s"].to_list()
    assert out == ["confirmed", "confirmed", "price_only", "candidate"]  # 40 for 100: neither agrees nor contradicts


def test_price_contradicting_the_ratio_is_conflicting_whatever_the_sources() -> None:
    # ITUB4 2011-11-01: B3 and a filing report 1:100, the price moved by 1.02 (a simultaneous 100:1 split)
    df = pl.DataFrame(
        {
            "sources": ["b3_company_events,cvm_ipe", "b3_company_events", "yahoo_chart"],
            "move": [1.0187, 0.0101, 1.01],
            "net": [0.01, 0.01, 1.05],  # the last: a 5 % bonus inside the noise, never contradicted
        }
    )
    got = df.select(events.status(pl.col("sources"), pl.col("move"), pl.col("net")).alias("s"))["s"].to_list()
    assert got == ["conflicting", "confirmed", "price_only"]
