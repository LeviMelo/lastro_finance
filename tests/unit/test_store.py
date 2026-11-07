"""Invariant 1 (raw is immutable, content-addressed), the manifest and the run record (PLAN §4.1, §4.2, §4.12)."""

from __future__ import annotations

import hashlib
import io
import json
import os
import stat

import httpx
import polars as pl
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from conftest import FIXTURES
from fin.config import Zones
from fin.ingest.fetch import Fetcher, FetchSpec
from fin.ingest.http import FetchError, PoliteClient
from fin.store.journal import Journal
from fin.store.manifest import SCHEMA, Manifest, canonical_request
from fin.store.raw import RawStore, RawStoreError
from fin.store.runs import IngestRun, recover


def test_raw_round_trip_and_layout(zones: Zones) -> None:
    store = RawStore(zones.raw)
    data = b"COTAHIST header\r\n"
    ref = store.put_bytes(data, ".TXT")
    sha = hashlib.sha256(data).hexdigest()
    assert ref.sha256 == sha and ref.created
    assert ref.path == zones.raw / sha[:2] / f"{sha}.txt"
    assert store.read(sha) == data
    store.verify(sha)
    assert not os.access(ref.path, os.W_OK)  # read-only once written


def test_large_text_is_compressed_at_rest_and_read_back_exactly(zones: Zones) -> None:
    store = RawStore(zones.raw)
    data = (FIXTURES / "b3_cotahist" / "COTAHIST_A2025_excerpt.TXT").read_bytes()
    assert len(data) >= 64 * 1024
    ref = store.put_bytes(data, "txt")
    assert ref.path.name.endswith(".txt.zst") and ref.path.stat().st_size < len(data) / 3
    assert ref.sha256 == hashlib.sha256(data).hexdigest()  # named by the original bytes
    assert store.read(ref.sha256) == data
    store.verify(ref.sha256)
    again = store.put_stream(io.BytesIO(data), "txt")
    assert not again.created and again.path == ref.path
    zipped = store.put_bytes(b"PK" + data, "zip")  # archives are kept as they are
    assert zipped.path.suffix == ".zip"


def test_raw_put_is_idempotent_and_stream_equals_bytes(zones: Zones) -> None:
    store = RawStore(zones.raw)
    a = store.put_bytes(b"x" * 3_000_000, "bin")
    b = store.put_stream(io.BytesIO(b"x" * 3_000_000), "bin")
    assert a.sha256 == b.sha256 and a.created and not b.created
    assert [s for s, _ in store.iter_objects()] == [a.sha256]


def test_raw_detects_corruption(zones: Zones) -> None:
    store = RawStore(zones.raw)
    ref = store.put_bytes(b"payload", "txt")
    os.chmod(ref.path, stat.S_IWRITE | stat.S_IREAD)
    ref.path.write_bytes(b"tampered")
    with pytest.raises(RawStoreError):
        store.verify(ref.sha256)
    with pytest.raises(RawStoreError):
        store.put_bytes(b"payload", "txt")  # stored size 8 vs offered 7


@settings(max_examples=25, deadline=None)
@given(st.binary(max_size=4096))
def test_raw_round_trips_any_bytes(tmp_path_factory: pytest.TempPathFactory, data: bytes) -> None:
    store = RawStore(tmp_path_factory.mktemp("raw"))
    ref = store.put_bytes(data, "bin")
    assert store.read(ref.sha256) == data


def test_canonical_request_redacts_and_is_order_free() -> None:
    a = canonical_request({"url": "u", "params": {"b": 1, "token": "s3cret"}})
    b = canonical_request({"params": {"token": "other", "b": 1}, "url": "u"})
    assert a == b and "s3cret" not in a


def _client(handler: httpx.MockTransport) -> PoliteClient:
    return PoliteClient(transport=handler, min_interval=0, sleep=lambda _s: None)


def test_fetch_stores_then_conditional_304_points_to_same_object(zones: Zones) -> None:
    calls: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        if req.headers.get("If-None-Match") == '"v1"':
            return httpx.Response(304)
        return httpx.Response(200, content=b"a;b\r\n1;2\r\n", headers={"ETag": '"v1"', "Content-Type": "text/csv"})

    spec = FetchSpec("cvm_cia_cadastro", "cad_cia_aberta", "https://example.test/cad.csv", "csv")
    with IngestRun(zones, "test") as run:
        f = Fetcher(run, RawStore(zones.raw), _client(httpx.MockTransport(handler)), "1")
        first = f.fetch(spec)
        second = f.fetch(spec)
    assert first.new_object and first.row.http_status == 200
    assert second.row.http_status == 304 and second.row.raw_sha256 == first.row.raw_sha256
    assert calls[1].headers["If-None-Match"] == '"v1"'
    m = Manifest(zones.manifest).read()
    assert m.height == 2 and set(m["http_status"]) == {200, 304}
    assert m.schema["fetched_at"] == pl.Datetime("us", "UTC")
    assert list((zones.manifest).glob("part-*.parquet"))  # sealed on run exit
    assert not list((zones.manifest / "_journal").glob("*.jsonl"))


def test_fetch_error_is_an_error_not_an_empty_object(zones: Zones) -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(404, content=b"not found"))
    with IngestRun(zones, "test") as run:
        f = Fetcher(run, RawStore(zones.raw), _client(transport), "1")
        with pytest.raises(FetchError):
            f.fetch(FetchSpec("s", "d", "https://example.test/x", "bin"))
    assert Manifest(zones.manifest).read().height == 0
    assert list(RawStore(zones.raw).iter_objects()) == []


def test_http_retries_5xx_then_succeeds() -> None:
    n = {"i": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        n["i"] += 1
        return httpx.Response(503) if n["i"] < 3 else httpx.Response(200, content=b"ok")

    slept: list[float] = []
    c = PoliteClient(transport=httpx.MockTransport(handler), min_interval=0, sleep=slept.append)
    assert c.request("GET", "https://example.test/").content == b"ok"
    assert n["i"] == 3 and len(slept) == 2


def test_run_record_counts_and_status(zones: Zones) -> None:
    with IngestRun(zones, "test ok") as run:
        run.count("d", in_=10, out=9, quarantined=1)
    with pytest.raises(ValueError), IngestRun(zones, "test boom"):
        raise ValueError("boom")
    runs = Journal(zones.runs, __import__("fin.store.runs", fromlist=["SCHEMA"]).SCHEMA).read()
    ends = runs.filter(pl.col("event") == "end").sort("command")
    assert ends["status"].to_list() == ["failed", "ok"]
    assert json.loads(ends.filter(pl.col("command") == "test ok")["counts"][0]) == {
        "d": {"in": 10, "out": 9, "quarantined": 1}
    }


def test_crashed_run_journal_is_recovered(zones: Zones) -> None:
    j = Journal(zones.manifest, SCHEMA)
    j.append("20260101T000000Z-dead00", {"raw_sha256": "0" * 64, "source_id": "s", "http_status": 200})
    runs = Journal(zones.runs, __import__("fin.store.runs", fromlist=["SCHEMA"]).SCHEMA)
    runs.append(
        "20260101T000000Z-dead00", {"ingest_run_id": "20260101T000000Z-dead00", "event": "start", "status": "running"}
    )
    assert recover(zones) == ["20260101T000000Z-dead00"]
    assert Manifest(zones.manifest).read().height == 1
    assert (zones.manifest / "part-20260101T000000Z-dead00.parquet").exists()
