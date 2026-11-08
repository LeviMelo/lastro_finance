"""B3 TaxaSwap.txt: three fixed-width eras, read statically out of the nested zip/self-extractor; DIC checked
against B3's web CSV."""

from __future__ import annotations

import io
import zipfile
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import polars as pl
import pytest

from fin.ingest import b3_taxaswap as ts
from fin.ingest.base import NotData

FIX = Path(__file__).parents[1] / "fixtures" / "b3_reference_rates"
ROW: dict[str, Any] = {
    "raw_sha256": "a" * 64,
    "ingest_run_id": "r",
    "dataset_id": "TS",
    "source_reference_date": date(2026, 11, 6),
}


def _parse(name: str) -> pl.DataFrame:
    good, bad = ts.SWAP_RATE.split(ts.parse_taxa_swap((FIX / name).read_bytes(), ROW))
    assert bad.height == 0
    return good


def test_2026_era_72_chars_pre_and_dic() -> None:
    df = _parse("TaxaSwap_20261106_PRE_DIC.txt")
    assert df.height == 564 and df.group_by("curve_code").len().sort("curve_code")["len"].to_list() == [282, 282]
    first = df.filter(pl.col("curve_code") == "PRE").row(0, named=True)
    assert (first["calendar_days"], first["business_days"], first["value"]) == (3, 1, Decimal("13.65"))
    assert first["vertex_type"] == "F" and first["vertex_nominal"] == 1 and first["curve_description"] == "DIxPRE"
    assert first["file_date"] == date(2026, 11, 6) and first["raw_locator"].startswith("line=")


def test_2018_era() -> None:
    df = _parse("TaxaSwap_20180102_PRE.txt")
    assert df.height == 318 and set(df["ref_date"]) == {date(2018, 1, 2)}
    assert df["vertex_type"].is_in(["F", "M"]).all()


def test_2000_era_65_chars_has_no_vertex_type_and_a_12_digit_value() -> None:
    df = _parse("TaxaSwap_20000114_full.txt")
    assert df.height == 492 and set(df["ref_date"]) == {date(2000, 1, 14)}
    assert df["vertex_type"].null_count() == df.height and df["vertex_nominal"].null_count() == df.height
    pre = df.filter(pl.col("curve_code") == "PRE")
    assert pre.height == 41 and pre["value"].min() > 0  # type: ignore[operator]


def test_dic_is_identical_to_the_web_csv_and_pre_to_two_decimals() -> None:
    csv = (FIX / "ReferenceRates_DIC_20261106.csv").read_bytes().decode("latin-1").splitlines()[1:]
    web = [(int(du), int(dc), Decimal(r.replace(",", "."))) for _, du, dc, r in (x.split(";") for x in csv)]
    ours = _parse("TaxaSwap_20261106_PRE_DIC.txt")
    dic = ours.filter(pl.col("curve_code") == "DIC")
    assert [(b, c, v) for c, b, v in dic.select("calendar_days", "business_days", "value").iter_rows()] == web
    pre_csv = (FIX / "ReferenceRates_PRE_20261106.csv").read_bytes().decode("latin-1").splitlines()[1:]
    pre_web = [Decimal(x.split(";")[3].replace(",", ".")) for x in pre_csv]
    pre = ours.filter(pl.col("curve_code") == "PRE")["value"].to_list()
    assert all(abs(a - b) <= Decimal("0.005") for a, b in zip(pre, pre_web, strict=True))


def test_nested_zip_is_read_statically() -> None:
    text = (FIX / "TaxaSwap_20180102_PRE.txt").read_bytes()
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as z:
        z.writestr("TAXASWAP.TXT", text)  # member casing varies by year
    exe = b"MZ" + b"\x00" * 100 + inner.getvalue()  # a PKSFX-like prefix: the zip reader skips it
    outer = io.BytesIO()
    with zipfile.ZipFile(outer, "w") as z:
        z.writestr("TS180102.ex_", exe)
    assert ts.taxa_swap_text(outer.getvalue()) == text
    (p,) = ts.parse_payload(outer.getvalue(), ROW | {"source_reference_date": date(2018, 1, 2)})
    assert p.partition == "ref_date=2018-01-02" and p.frame.height == 318


def test_not_a_zip_and_other_families_are_not_parsed() -> None:
    assert list(ts.parse_payload(b"anything", ROW | {"dataset_id": "PR"})) == []
    with pytest.raises(NotData):
        ts.taxa_swap_text(b"not a zip at all")


def test_unknown_width_is_refused() -> None:
    with pytest.raises(ts.LayoutError):
        ts.parse_taxa_swap(b"0000010010120261106T1PRE  DIxPRE         0000300001+000001365000\r\n", ROW)
