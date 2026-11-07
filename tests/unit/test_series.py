"""Series parsers read real SGS, Ipeadata and SIDRA payloads exactly; the core table labels periods by frequency,
carries the unit on every row, keeps one version per change, and quarantines a series without a definition."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import polars as pl
import pytest

from fin.config import Zones
from fin.ingest import series
from fin.ingest.base import NotData
from fin.ingest.fetch import Fetcher, FetchSpec
from fin.ingest.http import FetchError, PoliteClient
from fin.store.raw import RawStore
from fin.store.runs import IngestRun
from fin.store.tables import write_parquet

FIX = Path(__file__).parents[1] / "fixtures"
T0 = datetime(2026, 11, 7, 20, 0, tzinfo=UTC)


def _row(dataset_id: str, url: str = "https://example.test/", at: datetime = T0, sha: str = "a" * 64) -> dict[str, Any]:
    return {
        "raw_sha256": sha,
        "ingest_run_id": "run-1",
        "fetched_at": at,
        "dataset_id": dataset_id,
        "request": json.dumps({"url": url}),
    }


def _ok(contract: series.Contract, df: pl.DataFrame) -> pl.DataFrame:
    good, bad = contract.split(df)
    assert bad.height == 0, bad
    return good


def test_sgs_metadata_gives_name_frequency_and_unit() -> None:
    d = _ok(series.DEFINITION, series.parse_sgs_meta((FIX / "bcb_sgs/meta_433.xml").read_bytes(), _row("sgs_meta")))
    r = d.row(0, named=True)
    assert r["series_id"] == "bcb_sgs:433" and r["frequency"] == "M" and r["unit"] == "Var. % mensal"
    assert "IPCA" in r["name"]
    tr = series.parse_sgs_meta((FIX / "bcb_sgs/meta_226.xml").read_bytes(), _row("sgs_meta"))
    assert tr["frequency"][0] == "D" and tr["unit"][0] == "% a.m."


def test_sgs_nulls_are_marked_missing_not_quarantined() -> None:
    df = _ok(series.OBSERVATION, series.parse_sgs((FIX / "bcb_sgs/m2_27810_all.json").read_bytes(), _row("x"), "27810"))
    first = df.row(0, named=True)
    assert first["vt_date"] == date(2001, 8, 1) and first["value"] is None and first["value_text"] == ""
    assert df["value"][-1] == Decimal("7870395191")


def test_sgs_error_page_served_as_200_is_not_data() -> None:
    with pytest.raises(NotData):
        series.parse_sgs((FIX / "bcb_sgs/blocked_page_200.html").read_bytes(), _row("sgs_25"), "25")


def test_fetch_rejects_a_content_type_it_did_not_ask_for(zones: Zones) -> None:
    page = (FIX / "bcb_sgs/blocked_page_200.html").read_bytes()
    t = httpx.MockTransport(lambda r: httpx.Response(200, content=page, headers={"Content-Type": "text/html"}))
    client = PoliteClient(transport=t, min_interval=0, sleep=lambda _s: None)
    spec = FetchSpec("bcb_sgs", "sgs_25", "https://example.test/x", "json", content_types=("application/json",))
    with IngestRun(zones, "test") as run, pytest.raises(FetchError):
        Fetcher(run, RawStore(zones.raw), client, "1").fetch(spec)
    assert list(RawStore(zones.raw).iter_objects()) == []


def test_ipeadata_values_are_exact_and_metadata_frequency_is_mapped() -> None:
    obs = _ok(series.OBSERVATION, series.parse_ipeadata((FIX / "ipeadata/IGP12_IGPM12.json").read_bytes(), _row("x")))
    last = obs.filter(pl.col("vt_date") == date(2026, 10, 1)).row(0, named=True)
    assert last["series_id"] == "ipeadata:IGP12_IGPM12" and last["value"] == Decimal("1243.905")
    meta = series.parse_ipeadata_meta((FIX / "ipeadata/meta_IGP12_IGPM12.json").read_bytes(), _row("meta"))
    assert meta["frequency"][0] == "M"
    embi = series.parse_ipeadata_meta((FIX / "ipeadata/meta_JPM366_EMBI366.json").read_bytes(), _row("meta"))
    assert embi["frequency"][0] == "D"


SIDRA = "https://apisidra.ibge.gov.br/values/"


def test_sidra_rolling_quarter_and_class_series() -> None:
    blob = (FIX / "ibge_sidra/t6381_v4099_all.json").read_bytes()
    obs, defs = series.parse_sidra(blob, _row("x", SIDRA + "t/6381/n1/all/v/4099/p/all"))
    assert defs.row(0, named=True)["frequency"] == "M3" and defs["unit"][0] == "%"
    last = obs.row(-1, named=True)
    assert last["series_id"] == "ibge_sidra:6381/v4099" and last["vt_date"] == date(2026, 9, 1)
    assert last["value"] == Decimal("5.2")

    url = SIDRA + "t/5932/n1/all/v/6564,6561/p/all/c11255/90707"
    obs, defs = series.parse_sidra((FIX / "ibge_sidra/t5932_v6564_6561_c11255_all.json").read_bytes(), _row("x", url))
    obs = _ok(series.OBSERVATION, obs)
    assert set(defs["series_id"]) == {"ibge_sidra:5932/v6564/c11255/90707", "ibge_sidra:5932/v6561/c11255/90707"}
    assert set(defs["frequency"]) == {"Q"}
    missing = obs.filter(pl.col("value").is_null())
    assert missing["value_text"].to_list() == ["..."]


def _obs(sid: str, d: date, value: str, at: datetime, sha: str) -> dict[str, Any]:
    return {
        "series_id": sid,
        "vt_date": d,
        "vt_until": None,
        "period_text": str(d),
        "value_text": value,
        "raw_locator": "$[0]",
    } | {"_at": at, "_sha": sha}


def _staging(rows: list[dict[str, Any]]) -> pl.DataFrame:
    frames = [
        series._observations(  # pyright: ignore[reportPrivateUsage]
            [{k: v for k, v in r.items() if not k.startswith("_")}], _row("x", at=r["_at"], sha=r["_sha"])
        )
        for r in rows
    ]
    return series.OBSERVATION.conform(pl.concat(frames))


def test_versions_keep_first_value_and_each_change() -> None:
    d, s = date(2026, 9, 1), "bcb_sgs:433"
    t = [datetime(2026, 11, k, tzinfo=UTC) for k in (1, 2, 3, 4)]
    df = _staging(
        [
            _obs(s, d, "0.82", t[0], "1" * 64),
            _obs(s, d, "0.82", t[1], "2" * 64),
            _obs(s, d, "0.83", t[2], "3" * 64),
            _obs(s, d, "0.82", t[3], "4" * 64),
        ]
    )
    v = series.versions(df)
    assert v["value"].to_list() == [Decimal("0.82"), Decimal("0.83"), Decimal("0.82")]
    assert v["version"].to_list() == [1, 2, 3] and v["raw_sha256"].to_list() == ["1" * 64, "3" * 64, "4" * 64]


def test_core_labels_periods_and_quarantines_series_without_definition(zones: Zones) -> None:
    src = zones.staging / "bcb_sgs"
    sgs = series.parse_sgs((FIX / "bcb_sgs/tr_226_2026-10-08_2026-11-07.json").read_bytes(), _row("sgs_226"), "226")
    write_parquet(_ok(series.OBSERVATION, sgs), src / "observation" / "sgs_226" / "a.parquet")
    orphan = _staging([_obs("bcb_sgs:999", date(2026, 9, 1), "1", T0, "b" * 64)])
    write_parquet(orphan, src / "observation" / "sgs_999" / "b.parquet")
    meta = series.parse_sgs_meta((FIX / "bcb_sgs/meta_226.xml").read_bytes(), _row("sgs_meta"))
    write_parquet(_ok(series.DEFINITION, meta), src / "definition" / "code=226" / "c.parquet")

    good, bad = series.build_core(zones, "bcb_sgs")
    assert (good, bad) == (sgs.height, 1)
    core = pl.read_parquet(zones.core / "series_observation" / "source=bcb_sgs.parquet")
    first = core.row(0, named=True)
    assert first["vt_reference"] == "2026-10-08..2026-11-07" and first["vt_end"] == date(2026, 11, 7)
    assert set(core["unit"]) == {"% a.m."} and core["vt_reference"].n_unique() == core.height
    q = pl.read_parquet(zones.quarantine / "core" / "series_observation" / "source=bcb_sgs.parquet")
    assert q["series_id"].to_list() == ["bcb_sgs:999"]


def test_period_labels_per_frequency() -> None:
    df = pl.DataFrame(
        {
            "f": ["D", "M", "Q", "A", "M3", "M"],
            "d": [
                date(2024, 3, 15),
                date(2024, 3, 1),
                date(2024, 4, 1),
                date(2024, 1, 1),
                date(2024, 3, 1),
                date(2024, 3, 15),
            ],
        }
    )
    out = df.select(*series._period(pl.col("f"), pl.col("d"), pl.lit(None, dtype=pl.Date)))  # pyright: ignore[reportPrivateUsage]
    assert out["vt_reference"].to_list() == ["2024-03-15", "2024-03", "2024Q2", "2024", "2024-01..2024-03", "2024-03"]
    assert out["vt_end"].to_list()[:5] == [
        date(2024, 3, 15),
        date(2024, 3, 31),
        date(2024, 6, 30),
        date(2024, 12, 31),
        date(2024, 3, 31),
    ]
    assert out["_aligned"].to_list() == [True, True, True, True, True, False]


def test_vna_reads_text_cells_and_zero_means_matured() -> None:
    obs, defs = series.parse_tesouro_vna((FIX / "tesouro_vna/vna_ntnc.xlsx").read_bytes(), _row("vna_ntnc"))
    obs = _ok(series.OBSERVATION, obs)
    assert set(defs["series_id"]) == {"tesouro_vna:NTN-C/2005+2008+2011+2017+2021+2031", "tesouro_vna:NTN-C/2002+2006"}
    text = obs.filter(pl.col("vt_date") == date(2018, 1, 1), pl.col("series_id").str.ends_with("2031")).row(
        0, named=True
    )
    assert text["value"] == Decimal("3580.282456") and text["value_text"] == "\xa03.580,282456"
    old = obs.filter(pl.col("series_id") == "tesouro_vna:NTN-C/2002+2006", pl.col("vt_date") > date(2006, 12, 1))
    assert old["value"].null_count() == old.height and set(old["missing_reason"]) == {
        "VNA 0: the group's bonds have matured"
    }


def test_vna_ntnb_is_ipca_ratio_truncated() -> None:
    """VNA NTN-B = trunc(1000 × IPCA(m−1) / IPCA(Jun-2000), 6 dp), measured exact on 315 of 316 months."""
    obs, _ = series.parse_tesouro_vna((FIX / "tesouro_vna/vna_ntnb.xlsx").read_bytes(), _row("vna_ntnb"))
    ipca = json.loads((FIX / "ibge_sidra/t1737_v2266_all.json").read_bytes())[1:]
    index = {it["D3C"]: Decimal(it["V"]) for it in ipca}
    oct26 = obs.filter(pl.col("vt_date") == date(2026, 10, 15))["value"][0]
    expected = (Decimal(1000) * index["202609"] / index["200006"]).quantize(Decimal("0.000001"), rounding="ROUND_DOWN")
    assert oct26 == expected == Decimal("4766.335112")


def test_exponent_notation_is_written_out_exactly() -> None:
    obs = _ok(series.OBSERVATION, series.parse_ipeadata((FIX / "ipeadata/IGP12_IGPM12.json").read_bytes(), _row("x")))
    row = obs.filter(pl.col("value_text") == "3.08619E-05").row(0, named=True)
    assert row["value"] == Decimal("0.0000308619")
    with pytest.raises(series.LayoutError):
        series._plain("0." + "1" * 25)  # pyright: ignore[reportPrivateUsage]


def test_treasury_tenors_and_late_columns() -> None:
    url = "https://home.treasury.gov/x"
    obs, defs = series.parse_us_treasury(
        (FIX / "us_treasury/par_2025.csv").read_bytes(), _row("daily_treasury_yield_curve", url)
    )
    obs = _ok(series.OBSERVATION, obs)
    assert "us_treasury:par/1.5M" in set(defs["series_id"]) and set(defs["unit"]) == {"% p.a. (bond-equivalent)"}
    first_15 = obs.filter(pl.col("series_id") == "us_treasury:par/1.5M")["vt_date"].min()
    assert first_15 == date(2025, 2, 18)  # an empty cell before the tenor existed yields no row
    real = series.parse_us_treasury(
        (FIX / "us_treasury/real_2026.csv").read_bytes(), _row("daily_treasury_real_yield_curve", url)
    )[0]
    r = real.filter(pl.col("series_id") == "us_treasury:real/10Y", pl.col("vt_date") == date(2026, 11, 6))
    assert r["value"][0] == Decimal("2.63")


def test_nyfed_na_is_missing_and_flags_are_not_series() -> None:
    obs, defs = series.parse_nyfed((FIX / "nyfed/sofr_search.csv").read_bytes(), _row("secured_sofr"))
    obs = _ok(series.OBSERVATION, obs)
    na = obs.filter(pl.col("value_text") == "NA")
    assert na.height == 8 and na["value"].null_count() == 8
    assert not any("Footnote" in s or "Revision" in s for s in defs["source_code"])
    last = obs.filter(pl.col("series_id") == "nyfed:SOFR/rate").sort("vt_date")["value"][-1]
    assert last == Decimal("3.92")


def test_cboe_single_column_is_the_close() -> None:
    obs, defs = series.parse_cboe((FIX / "cboe/VVIX_History.csv").read_bytes(), _row("vvix"))
    assert set(defs["series_id"]) == {"cboe:VVIX/CLOSE"}
    assert obs.row(0, named=True)["value"] == Decimal("71.73")
