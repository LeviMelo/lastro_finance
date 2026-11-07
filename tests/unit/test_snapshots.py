"""The daily snapshot connectors plan the right requests: windows from the calendar, pagination from page 1,
404 outside a window is absence and not an error (PLAN §4.1 invariant 13)."""

from __future__ import annotations

import json
from datetime import date

import httpx
import pytest

from conftest import FIXTURES
from fin.config import Zones
from fin.ingest import snapshots
from fin.ingest.anbima_calendar import parse_holidays
from fin.ingest.base import Mode, run_connector
from fin.ingest.fetch import FetchSpec
from fin.reference.calendar import build_calendar_days
from fin.store.manifest import Manifest
from fin.store.runs import IngestRun
from fin.store.tables import write_parquet


@pytest.fixture
def calendar_zones(zones: Zones, monkeypatch: pytest.MonkeyPatch) -> Zones:
    blob = (FIXTURES / "anbima_calendar" / "feriados_nacionais.xls").read_bytes()
    days = build_calendar_days(parse_holidays(blob).select("date", "name"), "fixture")
    write_parquet(days, zones.core / "reference" / "calendar_day" / "calendar_day.parquet")
    monkeypatch.setattr(snapshots, "today_brt", lambda: date(2026, 11, 7))  # a Saturday
    return zones


def test_anbima_window_urls(calendar_zones: Zones) -> None:
    specs = list(snapshots.AnbimaTitulosPublicos().discover(Mode.SNAPSHOT, calendar_zones))
    txt = [s.url.rsplit("/", 1)[1] for s in specs if s.dataset_id == "ms_txt"]
    xls = [s.url.rsplit("/", 1)[1] for s in specs if s.dataset_id == "ms_xls"]
    assert txt[0] == "ms261106.txt" and xls[0] == "m26nov06.xls"
    assert "ms261102.txt" not in txt  # Finados, 2026-11-02
    assert "m26out29.xls" in xls
    assert all(s.absent_status == frozenset({404}) for s in specs)


def test_bdi_follows_page_count_from_real_response(calendar_zones: Zones) -> None:
    c = snapshots.B3Bdi()
    first = next(iter(c.discover(Mode.SNAPSHOT, calendar_zones)))
    assert first.reference_date == date(2026, 11, 6) and first.url.endswith("/2026-11-06/2026-11-06/1/1000")
    blob = (FIXTURES / "b3_settlement_prices" / "bdi_ConsolidatedTradesDerivatives_20261106_p1_take5.json").read_bytes()
    pages = json.loads(blob)["table"]["pageCount"]
    follow = list(c.follow(first, blob))
    assert len(follow) == pages - 1 and follow[-1].locator == f"page={pages}"
    assert list(c.follow(follow[0], blob)) == []  # only page 1 fans out


def test_absent_day_is_not_an_error(calendar_zones: Zones, monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x@y\r\n") if "ms261106" in str(req.url) else httpx.Response(404)

    real = httpx.Client

    def client(*a: object, **k: object) -> httpx.Client:
        k["transport"] = httpx.MockTransport(handler)
        return real(*a, **k)  # type: ignore[arg-type]

    monkeypatch.setattr(httpx, "Client", client)
    c = snapshots.AnbimaTitulosPublicos()
    monkeypatch.setattr(c, "min_interval", 0)
    with IngestRun(calendar_zones, "test") as run:
        assert run_connector(c, calendar_zones, run, Mode.SNAPSHOT) == 0
        assert not run.errors
    m = Manifest(calendar_zones.manifest).read()
    assert m["source_reference_date"].to_list() == [date(2026, 11, 6)]


def test_fetchspec_request_identity_includes_json_body() -> None:
    a = FetchSpec("s", "d", "u", "json", method="POST", json={})
    b = FetchSpec("s", "d", "u", "json", method="POST", json={"x": 1})
    assert a.request() != b.request()
