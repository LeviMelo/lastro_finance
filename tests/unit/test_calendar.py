"""The ANBIMA calendar against its own file and against an independent source: BCB publishes CDI on every business
day and only then (docs/sources/bcb_sgs.md), and BCB's published accumulated factors reproduce under du = [a, b)."""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

import polars as pl
import pytest
from hypothesis import given
from hypothesis import strategies as st

from conftest import FIXTURES
from fin.ingest.anbima_calendar import parse_holidays
from fin.reference.calendar import Calendar, CalendarRangeError, build_calendar_days

XLS = (FIXTURES / "anbima_calendar" / "feriados_nacionais.xls").read_bytes()


@pytest.fixture(scope="module")
def cal() -> Calendar:
    return Calendar.from_frame(build_calendar_days(parse_holidays(XLS).select("date", "name"), "fixture"))


def cdi(name: str) -> list[tuple[date, Decimal]]:
    rows = json.loads((FIXTURES / "bcb_sgs" / name).read_text(encoding="utf-8"))
    return [(datetime.strptime(r["data"], "%d/%m/%Y").date(), Decimal(r["valor"])) for r in rows]


def test_holiday_file_as_measured_in_recon() -> None:
    h = parse_holidays(XLS)
    assert h.height == 1264
    assert h["date"].min() == date(2001, 1, 1) and h["date"].max() == date(2099, 12, 25)
    per_year = h.group_by(pl.col("date").dt.year().alias("y")).len().sort("y")
    assert set(per_year.filter(pl.col("y") <= 2023)["len"]) == {12}
    assert set(per_year.filter(pl.col("y") >= 2024)["len"]) == {13}
    assert h.filter(pl.col("date") == date(2026, 11, 20))["name"][0].startswith("Dia Nacional de Zumbi")
    assert not h["name"].str.ends_with(" ").any()


def test_cdi_dates_are_exactly_the_business_days(cal: Calendar) -> None:
    for name in ("cdi_2024q1.json", "cdi2024_25.json"):
        obs = [d for d, _ in cdi(name)]
        assert obs == cal.business_days(obs[0], obs[-1]), name


def test_bcb_accumulated_cdi_factor_reproduces_under_du_convention(cal: Calendar) -> None:
    rates = dict(cdi("cdi2024_25.json"))
    for start, end, published in (
        (date(2024, 1, 2), date(2024, 4, 1), Decimal("1.02621059")),
        (date(2024, 1, 2), date(2025, 1, 2), Decimal("1.10875983")),
    ):
        days = cal.business_days(start, cal.add_business_days(end, -1))
        assert len(days) == cal.du(start, end)
        f = Decimal(1)
        for d in days:
            f *= 1 + rates[d] / 100
        assert f.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP) == published


def test_du_and_shifts(cal: Calendar) -> None:
    assert cal.du(date(2026, 11, 19), date(2026, 11, 23)) == 1  # Fri 20/11 Consciência Negra, weekend
    assert cal.du(date(2026, 11, 23), date(2026, 11, 19)) == -1
    assert not cal.is_business_day(date(2026, 11, 20))
    assert cal.following(date(2026, 11, 20)) == date(2026, 11, 23)
    assert cal.preceding(date(2026, 11, 22)) == date(2026, 11, 19)
    assert cal.add_business_days(date(2026, 11, 19), 1) == date(2026, 11, 23)
    with pytest.raises(CalendarRangeError):
        cal.du(date(2000, 12, 29), date(2001, 1, 3))


@given(
    st.dates(date(2001, 1, 1), date(2099, 12, 31)),
    st.dates(date(2001, 1, 1), date(2099, 12, 31)),
    st.dates(date(2001, 1, 1), date(2099, 12, 31)),
)
def test_du_is_additive_and_antisymmetric(a: date, b: date, c: date) -> None:
    cal = _CAL
    assert cal.du(a, b) + cal.du(b, c) == cal.du(a, c)
    assert cal.du(a, b) == -cal.du(b, a)


_CAL = Calendar.from_frame(build_calendar_days(parse_holidays(XLS).select("date", "name"), "fixture"))


def test_extend_back_with_publication_days_keeps_du_continuous() -> None:
    from datetime import date as d

    from fin.reference.calendar import build_calendar_days, extend_back

    days = build_calendar_days(pl.DataFrame({"date": [d(2001, 1, 1)], "name": ["Confraternização Universal"]}), "v")
    full = extend_back(days, [d(2000, 12, 27), d(2000, 12, 28), d(2000, 12, 29)])
    pre = full.filter(pl.col("basis") == "bcb_sgs_12")
    assert pre["date"].min() == d(2000, 12, 27) and pre["is_anbima_business_day"].sum() == 3
    # 2001-01-02 (the first ANBIMA business day) has the three publication days before it
    assert full.filter(pl.col("date") == d(2001, 1, 2))["du_index"][0] == 3
