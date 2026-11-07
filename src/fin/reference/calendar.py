"""The canonical business-day calendar (PLAN §4.1 invariant 9, §4.3.1 `calendar_day`, §4.9).

Built from ANBIMA's national holidays file only (never a library's holiday set). A business day is a weekday that is
not an ANBIMA national holiday. `du_index` is the number of business days strictly before the date, counted from
the calendar's first date, so the business days in [a, b) are `du_index[b] - du_index[a]`. That is the convention
of `du` in BUS/252 accrual (start counted, end not), and the one under which BCB's published CDI factors reproduce
(docs/sources/bcb_sgs.md).

`calendar_version` is the SHA-256 of the holidays file the calendar was built from.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from datetime import date, timedelta

import polars as pl

from fin.schema import Column, Contract

CALENDAR_DAY = Contract(
    table="core.reference.calendar_day",
    version=1,
    description="Every calendar date the ANBIMA holiday file covers, with business-day flags and the du ordinal.",
    columns=(
        Column("date", pl.Date, "calendar date", "data", "date", nullable=False),
        Column("weekday", pl.Int8, "ISO weekday, 1 = Monday", "dia da semana ISO", "1-7", nullable=False),
        Column(
            "is_anbima_business_day",
            pl.Boolean,
            "weekday and not an ANBIMA national holiday",
            "dia útil ANBIMA",
            nullable=False,
        ),
        Column("is_b3_trading_day", pl.Boolean, "B3 held a session; null until observed (OPEN_QUESTIONS)", "pregão B3"),
        Column(
            "holiday_name",
            pl.String,
            "ANBIMA holiday name, also when the holiday falls on a weekend",
            "nome do feriado",
        ),
        Column(
            "du_index",
            pl.Int32,
            "business days strictly before this date since the first date",
            "ordinal de dias úteis",
            "business days",
            nullable=False,
        ),
        Column(
            "calendar_version",
            pl.String,
            "SHA-256 of the holidays file this row was built from",
            "versão do calendário",
            nullable=False,
        ),
    ),
    key=("date",),
    provenance=False,
)


class CalendarRangeError(ValueError):
    """A date outside the calendar's coverage; the calendar never guesses beyond its source."""


def build_calendar_days(holidays: pl.DataFrame, version: str) -> pl.DataFrame:
    """`holidays` has columns `date` and `name`. Covers Jan 1 of the first year to Dec 31 of the last."""
    first = date(holidays["date"].min().year, 1, 1)  # type: ignore[union-attr]
    last = date(holidays["date"].max().year, 12, 31)  # type: ignore[union-attr]
    days = pl.DataFrame({"date": pl.date_range(first, last, "1d", eager=True)})
    names = holidays.group_by("date").agg(pl.col("name").str.join(" / ").alias("holiday_name"))
    df = (
        days.join(names, on="date", how="left")
        .with_columns(pl.col("date").dt.weekday().cast(pl.Int8).alias("weekday"))
        .with_columns(((pl.col("weekday") <= 5) & pl.col("holiday_name").is_null()).alias("is_anbima_business_day"))
        .sort("date")
        .with_columns(
            (
                pl.col("is_anbima_business_day").cast(pl.Int32).cum_sum()
                - pl.col("is_anbima_business_day").cast(pl.Int32)
            ).alias("du_index"),
            pl.lit(None, dtype=pl.Boolean).alias("is_b3_trading_day"),
            pl.lit(version).alias("calendar_version"),
        )
    )
    return CALENDAR_DAY.conform(df)


@dataclass(frozen=True)
class Calendar:
    first: date
    last: date
    version: str
    _business: tuple[date, ...]  # sorted business days

    @classmethod
    def from_frame(cls, df: pl.DataFrame) -> Calendar:
        df = df.sort("date")
        bdays = tuple(df.filter(pl.col("is_anbima_business_day"))["date"].to_list())
        versions = df["calendar_version"].unique().to_list()
        if len(versions) != 1:
            raise ValueError(f"calendar frame mixes versions {versions}")
        return cls(df["date"][0], df["date"][-1], versions[0], bdays)

    def _check(self, d: date) -> None:
        if not (self.first <= d <= self.last):
            raise CalendarRangeError(f"{d} is outside the calendar ({self.first} to {self.last})")

    def is_business_day(self, d: date) -> bool:
        self._check(d)
        i = bisect.bisect_left(self._business, d)
        return i < len(self._business) and self._business[i] == d

    def du(self, start: date, end: date) -> int:
        """Business days in [start, end); negative when end < start."""
        self._check(start)
        self._check(end)
        return bisect.bisect_left(self._business, end) - bisect.bisect_left(self._business, start)

    def business_days(self, start: date, end: date) -> list[date]:
        """Business days d with start <= d <= end."""
        self._check(start)
        self._check(end)
        return list(
            self._business[bisect.bisect_left(self._business, start) : bisect.bisect_right(self._business, end)]
        )

    def add_business_days(self, d: date, n: int) -> date:
        """The n-th business day after d (n > 0) or before it (n < 0); n = 0 rolls d forward to a business day."""
        self._check(d)
        if n >= 0:
            i = bisect.bisect_left(self._business, d) if n == 0 else bisect.bisect_right(self._business, d) + n - 1
        else:
            i = bisect.bisect_left(self._business, d) + n
        if not (0 <= i < len(self._business)):
            raise CalendarRangeError(f"{d} {n:+d} business days is outside the calendar")
        return self._business[i]

    def following(self, d: date) -> date:
        return self.add_business_days(d, 0)

    def preceding(self, d: date) -> date:
        self._check(d)
        i = bisect.bisect_right(self._business, d) - 1
        if i < 0:
            raise CalendarRangeError(f"no business day on or before {d}")
        return self._business[i]

    def days(self) -> list[date]:
        return [self.first + timedelta(days=i) for i in range((self.last - self.first).days + 1)]
