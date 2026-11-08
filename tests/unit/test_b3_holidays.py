"""B3's calendar page parses into dated closures; the future part of the calendar follows it."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl

from fin.ingest.b3_holidays import parse_page
from fin.reference.calendar import build_calendar_days, with_b3_schedule, with_sessions

PAGE = Path(__file__).parents[1] / "fixtures" / "b3_holidays" / "feriados_20261108.html"


def test_page_gives_closures_2021_to_2026() -> None:
    d = parse_page(PAGE.read_bytes(), {"raw_sha256": "a" * 64, "ingest_run_id": "r"})
    assert (d.height, int(d["equities_closed"].sum())) == (156, 73)
    # São Paulo's anniversary: B3 closed in 2021, has traded on it since 2022
    sp = dict(zip(*d.filter(pl.col("event").str.contains("Paulo")).select("date", "equities_closed"), strict=True))
    assert sp[date(2021, 1, 25)] is True and sp[date(2024, 1, 25)] is False
    assert d["date"].min() == date(2021, 1, 1) and d["date"].max() == date(2026, 12, 31)


def test_future_trading_days_follow_the_published_closures() -> None:
    days = build_calendar_days(pl.DataFrame({"date": [date(2026, 1, 1)], "name": ["Confraternização"]}), "v")
    days = with_sessions(days, [date(2026, 1, 2), date(2026, 1, 5)])
    out = with_b3_schedule(days, [date(2026, 1, 26)], date(2026, 12, 31)).filter(
        pl.col("date").is_between(date(2026, 1, 23), date(2026, 1, 27))
    )
    got = dict(zip(out["date"].to_list(), out["is_b3_trading_day"].to_list(), strict=True))
    assert got[date(2026, 1, 23)] is True and got[date(2026, 1, 26)] is False and got[date(2026, 1, 24)] is False
