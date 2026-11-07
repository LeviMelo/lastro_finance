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


def test_b3_files_follow_the_token_and_skip_weekends(calendar_zones: Zones) -> None:
    c = snapshots.B3Files()
    specs = list(c.discover(Mode.SNAPSHOT, calendar_zones))
    assert {s.params["fileName"] for s in specs if s.params} == set(c.FILES)
    first = specs[0]
    assert first.params == {"fileName": "InstrumentsConsolidatedFile", "date": "2026-11-06"}
    assert 400 in first.absent_status  # no-session days (2025-12-24, 2025-12-31)
    nxt = list(c.follow(first, b'{"redirectUrl":"~/download?token=abc","token":"abc"}'))
    assert len(nxt) == 1 and nxt[0].params == {"token": "abc"} and nxt[0].dataset_id == "InstrumentsConsolidatedFile"
    assert list(c.follow(first, b'{"redirectUrl":null,"token":null}')) == []
    assert list(c.follow(nxt[0], b"csv")) == []


def test_pesquisapregao_names_and_backfill_bounds(calendar_zones: Zones) -> None:
    c = snapshots.B3PesquisaPregao()
    daily = list(c.discover(Mode.SNAPSHOT, calendar_zones))
    names = {s.params["filelist"] for s in daily if s.params}
    assert "PR261106.zip," in names and "TS261106.ex_," in names
    back = list(c.discover(Mode.BACKFILL, calendar_zones, families=["PR"], years=[2018]))
    assert back[-1].params == {"filelist": "PR180102.zip,"}  # first served date, 2018-01-02
    assert all(s.dataset_id == "PR" for s in back)


def test_index_portfolio_requests_decode_to_the_documented_json(calendar_zones: Zones) -> None:
    import base64

    specs = list(snapshots.B3IndexPortfolio().discover(Mode.SNAPSHOT, calendar_zones))
    assert len(specs) == 14 * 3
    ibov = next(s for s in specs if s.dataset_id == "GetPortfolioDay" and s.locator == "index=IBOV")
    payload = json.loads(base64.b64decode(ibov.url.rsplit("/", 1)[1]))
    assert payload == {"language": "pt-br", "pageNumber": 1, "pageSize": 120, "index": "IBOV", "segment": "1"}
