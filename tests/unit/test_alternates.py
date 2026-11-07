"""The gap-closing connectors plan the right requests: SGS windows within BCB's 10-year cap and contiguous, SND months
from 1993-11, Fundos.NET paging that stops once a page is already held (daily) and walks everything (backfill)."""

from __future__ import annotations

import itertools
import json
from datetime import date, timedelta

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


def test_snd_backfill_months_and_snapshots(zones: Zones) -> None:
    specs = list(SndDebentures().discover(Mode.BACKFILL, zones))
    kinds = [s.dataset_id for s in specs]
    assert kinds.count("caracteristicas") == 1 and kinds.count("agenda") == 1
    precos = [s for s in specs if s.dataset_id == "precos"]
    assert precos[0].locator == "1993-11-01..1993-11-30"
    assert precos[-1].locator == "2026-11-01..2026-11-06"
    assert len(precos) == (2026 - 1993) * 12 + 1
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
