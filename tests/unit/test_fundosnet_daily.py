"""Fundos.NET ETF daily reports: the 2018 and 2022- layouts parse to the same contract, values exact."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from fin.ingest import fundosnet_daily as fd

FIX = Path(__file__).parents[1] / "fixtures" / "b3_fundosnet_daily"


def _parse(name: str, doc_id: int):
    row = {"raw_sha256": "x", "ingest_run_id": "r", "dataset_id": "informe_diario",
           "request": json.dumps({"params": {"id": doc_id}})}  # fmt: skip
    df = fd.parse_daily((FIX / name).read_bytes(), row)
    good, bad = fd.DAILY.split(df)
    assert bad.height == 0
    return good.row(0, named=True)


def test_2018_layout_takes_the_cnpj_from_the_header() -> None:
    r = _parse("informe_28656_2018.xml", 28656)
    assert (r["fund_cnpj"], r["reference_date"]) == ("13416245000146", date(2018, 6, 29))
    assert r["quota_value_brl"] == Decimal("38.405119") and r["net_assets_brl"] == Decimal("55687422.62")
    assert r["holders"] == 2919 and r["next_nav_date"] == date(2018, 7, 2)


def test_namespaced_layouts() -> None:
    r = _parse("informe_330290_2022.xml", 330290)
    assert (r["fund_cnpj"], r["reference_date"]) == ("31024153000100", date(2022, 7, 25))
    assert r["quota_value_brl"] == Decimal("82.534249") and r["next_nav_date"] is None
    b = _parse("informe_1339103_2026.xml", 1339103)
    assert b["fund_cnpj"] == "10406511000161" and b["quota_value_brl"] == Decimal("184.283831")
    assert b["subscriptions_brl"] == Decimal("119784490.15") and b["holders"] == 106027


def test_more_decimals_than_the_contract_fail_loudly() -> None:
    with pytest.raises(fd.LayoutError):
        fd._num("1,123456", 4, "PATRIM_LIQ")
