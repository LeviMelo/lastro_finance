"""The gap-closing connectors plan the right requests: SGS windows within BCB's 10-year cap and contiguous, SND months
from 1993-11, Fundos.NET paging that stops once a page is already held (daily) and walks everything (backfill)."""

from __future__ import annotations

import itertools
import json
from datetime import UTC, date, datetime, timedelta

import polars as pl
import pytest

from fin.config import Zones
from fin.ingest import alternates
from fin.ingest.alternates import BcbSgs, FundosNetRendimentos, SndDebentures, YahooChart, month_windows
from fin.ingest.base import Mode

TODAY = date(2026, 11, 7)


@pytest.fixture(autouse=True)
def _today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(alternates, "today_brt", lambda: TODAY)


def test_month_windows_cover_without_gaps() -> None:
    w = month_windows(date(1993, 11, 1), date(1994, 2, 10))
    assert w == [
        (date(1993, 11, 1), date(1993, 11, 30)),
        (date(1993, 12, 1), date(1993, 12, 31)),
        (date(1994, 1, 1), date(1994, 1, 31)),
        (date(1994, 2, 1), date(1994, 2, 10)),
    ]


def test_sgs_backfill_windows_are_contiguous_and_capped(zones: Zones) -> None:
    specs = [s for s in BcbSgs().discover(Mode.BACKFILL, zones) if s.dataset_id == "sgs_12"]
    spans = [tuple(date.fromisoformat(x) for x in (s.locator or "").split("..")) for s in specs]
    assert spans[0][0] == date(1986, 3, 6) and spans[-1][1] == TODAY
    for (a, b), (c, _) in itertools.pairwise(spans):
        assert c == b + timedelta(days=1)
        assert BcbSgs.add_years(a, 10) > b  # ≤ 10 years, inclusive (BCB answers 406 beyond)
    daily = [s for s in BcbSgs().discover(Mode.INCREMENTAL, zones) if s.dataset_id == "sgs_12"]
    assert len(daily) == 1 and daily[0].params and daily[0].params["dataFinal"] == "07/11/2026"


def test_snd_backfill_months_and_snapshots(zones: Zones, monkeypatch: pytest.MonkeyPatch) -> None:
    specs = list(SndDebentures().discover(Mode.BACKFILL, zones))
    kinds = [s.dataset_id for s in specs]
    assert kinds.count("caracteristicas") == 1 and kinds.count("agenda") == 1
    precos = [s for s in specs if s.dataset_id == "precos"]
    assert precos[0].locator == "1993-11-01..1993-11-30"
    assert precos[-1].locator == "2026-11-01..2026-11-06"
    assert len(precos) == (2026 - 1993) * 12 + 1
    held = {s.locator for s in precos if s.locator != "2020-12-01..2020-12-31"} | {"2020-12-01..2020-12-01"}
    monkeypatch.setattr(
        alternates,
        "_held",
        lambda *_: pl.DataFrame({"notes": sorted(held), "fetched_at": [datetime(2026, 11, 7, tzinfo=UTC)] * len(held)}),
    )
    retry = [s.locator for s in SndDebentures().discover(Mode.BACKFILL, zones) if s.dataset_id == "precos"]
    assert retry[:2] == ["2020-12-02..2020-12-02", "2020-12-03..2020-12-03"]  # a failed month, day by day
    assert len([r for r in retry if r and r.startswith("2020-12")]) == 30
    monkeypatch.undo()
    monkeypatch.setattr(alternates, "today_brt", lambda: TODAY)
    daily = [s for s in SndDebentures().discover(Mode.INCREMENTAL, zones) if s.dataset_id == "precos"]
    assert [s.locator for s in daily] == ["2026-10-28..2026-11-06"]
    assert daily[0].params and daily[0].params["dt_ini"] == "10/28/2026"  # SND reads month/day/year


def _page(ids: list[int], total: int) -> bytes:
    return json.dumps({"data": [{"id": i} for i in ids], "recordsFiltered": total}).encode()


def test_fundosnet_daily_stops_at_a_held_page(zones: Zones) -> None:
    c = FundosNetRendimentos()
    (first,) = list(c.discover(Mode.INCREMENTAL, zones))
    c._held_ids = {3, 4}  # pyright: ignore[reportPrivateUsage]
    out = list(c.follow(first, _page([1, 2], 1000)))  # all new: fetch both, page on
    assert [s.locator for s in out] == ["id=1", "id=2", "offset=200"]
    out = list(c.follow(out[-1], _page([3, 4], 1000)))  # all held: stop
    assert out == []
    out = list(c.follow(first, _page([5, 3], 1000)))  # partly held: fetch the new one, stop
    assert [s.locator for s in out] == ["id=5"]


def test_fundosnet_backfill_walks_every_page(zones: Zones) -> None:
    c = FundosNetRendimentos()
    (first,) = list(c.discover(Mode.BACKFILL, zones))
    c._held_ids = {1, 2}  # pyright: ignore[reportPrivateUsage]
    out = list(c.follow(first, _page([1, 2], 401)))
    assert [s.locator for s in out] == ["offset=200"]
    out = list(c.follow(out[-1], _page([7], 401)))
    assert [s.locator for s in out] == ["id=7", "offset=400"]
    assert list(c.follow(out[-1], _page([8], 401)))[-1].locator == "id=8"  # last page: no further listing


def test_yahoo_uses_given_tickers(zones: Zones) -> None:
    specs = list(YahooChart().discover(Mode.SNAPSHOT, zones, tickers=["ITUB4", "SLCE3"]))
    assert [s.url.rsplit("/", 1)[1] for s in specs] == ["ITUB4.SA", "SLCE3.SA"]
    assert specs[0].params == {"range": "max", "interval": "1d", "events": "div|split"}


def test_cvm_docs_backfill_then_weekly_and_monthly(zones: Zones, monkeypatch: pytest.MonkeyPatch) -> None:
    from fin.ingest.alternates import CvmDfpItr

    specs = list(CvmDfpItr().discover(Mode.BACKFILL, zones))
    assert [s.url.rsplit("/", 1)[1] for s in specs][:2] == ["dfp_cia_aberta_2010.zip", "dfp_cia_aberta_2011.zip"]
    assert sum(s.dataset_id == "itr_cia_aberta" for s in specs) == 2026 - 2011 + 1

    fetched = {
        "2026": date(2026, 11, 2),
        "2025": date(2026, 10, 30),
        "2024": date(2026, 10, 20),
        "2023": date(2026, 10, 1),
    }
    frame = pl.DataFrame(
        {
            "notes": list(fetched),
            "fetched_at": [datetime(d.year, d.month, d.day, tzinfo=UTC) for d in fetched.values()],
        }
    )
    monkeypatch.setattr(alternates, "_held", lambda *_: frame)
    due = [s.locator for s in CvmDfpItr().discover(Mode.INCREMENTAL, zones) if s.dataset_id == "dfp_cia_aberta"]
    # 2026: 5 days ago, not due; 2025: 8 days, weekly, due; 2024: 18 days, monthly, not due; 2023: 37 days, due;
    # 2022: never seen, due; 2021 and older: frozen, not re-requested by the daily job.
    assert due == ["2022", "2023", "2025"]


def test_context_catalogue_plans(zones: Zones, monkeypatch: pytest.MonkeyPatch) -> None:
    from fin.ingest import context
    from fin.ingest.registry import CONNECTORS

    monkeypatch.setattr(context, "today_brt", lambda: TODAY)
    treasury = CONNECTORS["us_treasury"]()
    back = list(treasury.discover(Mode.BACKFILL, zones))
    assert len(back) == 2 * (2026 - 1990 + 1)  # nominal and real curves, one file per year
    assert back[0].params and back[0].params["field_tdr_date_value"] == "1990"
    daily = list(treasury.discover(Mode.INCREMENTAL, zones))
    assert [s.params["field_tdr_date_value"] for s in daily if s.params] == [
        "2026",
        "2026",
    ]  # past years: backfill only

    nyfed = CONNECTORS["nyfed"]()
    first = list(nyfed.discover(Mode.INCREMENTAL, zones))
    assert first[0].params and first[0].params["startDate"] == "1990-01-01"  # nothing held: full history first
    held = pl.DataFrame({"notes": ["unsecured/effr"], "fetched_at": [datetime(2026, 11, 5, tzinfo=UTC)]})
    monkeypatch.setattr(context, "_held", lambda *_: held)
    again = list(nyfed.discover(Mode.INCREMENTAL, zones))
    assert again[0].params and again[0].params["startDate"] == "2026-10-08"  # then only the last 30 days

    sgs = [s for s in CONNECTORS["bcb_sgs"]().discover(Mode.INCREMENTAL, zones) if s.dataset_id == "sgs_433"]
    assert len(sgs) == 1  # the catalogue's monthly SGS series ride on the bcb_sgs connector

    wb = CONNECTORS["worldbank_cmo"]()
    page = b'<a href="https://thedocs.worldbank.org/en/doc/x/related/CMO-Historical-Data-Monthly.xlsx">x</a>'
    (spec,) = list(wb.discover(Mode.SNAPSHOT, zones))
    (link,) = list(wb.follow(spec, page))
    assert link.url.endswith("CMO-Historical-Data-Monthly.xlsx") and link.ext == "xlsx"
