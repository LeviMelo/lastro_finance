"""ANBIMA free files: layouts confirmed on the archived real bytes (fixtures), exact decimals, the stubs refused."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from math import exp
from pathlib import Path
from typing import Any

import polars as pl
import pytest

from fin.ingest import anbima_parsers as ap
from fin.ingest.base import NotData
from fin.schema import Contract

FIX = Path(__file__).parents[1] / "fixtures"


def _row(ds: str, ref: date | None = None) -> dict[str, Any]:
    return {"raw_sha256": "a" * 64, "ingest_run_id": "r", "dataset_id": ds, "source_reference_date": ref}


def _clean(df: pl.DataFrame, contract: Contract) -> pl.DataFrame:
    good, bad = contract.split(df)
    assert bad.height == 0
    return good


def _ettj() -> dict[str, pl.DataFrame]:
    frames = ap.parse_ettj((FIX / "anbima_ettj" / "CurvaZero_06112026.txt").read_bytes(), _row("curva_zero_txt"))
    return {k: _clean(v, ap.ETTJ_CONTRACTS[k]) for k, v in frames.items()}


def test_ettj_vertices_and_parameters() -> None:
    f = _ettj()
    assert {k: v.height for k, v in f.items()} == {
        "parameter": 2,
        "vertex": 65,
        "circular_vertex": 10,
        "bond_error": 31,
    }
    v = f["vertex"].filter(pl.col("business_days") == 1008).row(0, named=True)  # `1.008` is thousands, not a decimal
    assert v["ettj_ipca_pct"] == Decimal("7.8109") and v["ettj_pref_pct"] == Decimal("15.1385")
    assert f["vertex"].filter(pl.col("business_days") == 8316)["ettj_pref_pct"].null_count() == 1  # empty field
    p = f["parameter"].filter(pl.col("curve") == "PREFIXADOS").row(0, named=True)
    assert p["beta2"] == Decimal("-0.0075884442277111") and p["ref_date"] == date(2026, 11, 6)
    e = f["bond_error"].filter(pl.col("bond_type") == "NTN-B").row(0, named=True)
    assert (
        e["maturity_date"] == date(2027, 5, 15) and e["error_pct"] == Decimal("0.2291") and e["selic_code"] == "760199"
    )


def test_ettj_svensson_reproduces_published_vertices() -> None:
    """Units: betas are annual rates as fractions, t = business days / 252, lambdas multiply t."""
    f = _ettj()
    for curve, col in (("PREFIXADOS", "ettj_pref_pct"), ("IPCA", "ettj_ipca_pct")):
        b1, b2, b3, b4, l1, l2 = (float(x) for x in f["parameter"].filter(pl.col("curve") == curve).row(0)[2:8])
        for du in (252, 504, 2520):
            t = du / 252
            f1 = (1 - exp(-l1 * t)) / (l1 * t)
            f2 = (1 - exp(-l2 * t)) / (l2 * t)
            r = b1 + b2 * f1 + b3 * (f1 - exp(-l1 * t)) + b4 * (f2 - exp(-l2 * t))
            published = float(f["vertex"].filter(pl.col("business_days") == du)[col][0])
            assert abs(r * 100 - published) < 0.0003


def test_ettj_out_of_window_stub_is_not_data() -> None:
    with pytest.raises(NotData):
        ap.parse_ettj((FIX / "anbima_ettj" / "CurvaZero_out_of_window_error.txt").read_bytes(), _row("curva_zero_txt"))


def test_vna() -> None:
    df = _clean(ap.parse_vna((FIX / "anbima_vna" / "VNA_301026.txt").read_bytes(), _row("vna_txt")), ap.VNA)
    assert df.height == 3 and set(df["ref_date"]) == {date(2026, 10, 30)}
    ntnb = df.filter(pl.col("bond_type") == "NTN-B").row(0, named=True)
    assert ntnb["vna_brl"] == Decimal("4771.575461") and ntnb["index_status"] == "P"
    assert ntnb["valid_from"] == date(2026, 10, 26) and ntnb["index_pct"] == Decimal("0.21")
    lft = df.filter(pl.col("bond_type") == "LFT").row(0, named=True)  # ragged row: no Ref / Válido a partir de
    assert lft["vna_brl"] == Decimal("20201.049997") and lft["index_status"] is None and lft["valid_from"] is None


def test_vna_stub_is_not_data() -> None:
    with pytest.raises(NotData):
        ap.parse_vna((FIX / "anbima_vna" / "VNA_out_of_window_error.txt").read_bytes(), _row("vna_txt"))


def test_debentures() -> None:
    row = _row("db_txt", date(2026, 11, 6))
    df = _clean(ap.parse_debentures((FIX / "anbima_debentures" / "db261106.txt").read_bytes(), row), ap.DEBENTURE_RATE)
    assert df.height == 1270 and df["ticker"].n_unique() == 1270
    a = df.filter(pl.col("ticker") == "AALM12").row(0, named=True)
    assert a["issuer_name"] == "AURA ALMAS MINERACAO S.A." and a["name_marks"] == "(*)"
    assert (a["indexer"], a["spread_pct"]) == ("DI", Decimal("1.6")) and a["maturity_date"] == date(2030, 10, 2)
    assert a["price_brl"] == Decimal("1027.456224") and a["duration_bdays"] == Decimal("505.67")
    assert a["reune_pct"] is None and a["bid_rate_pct"] == Decimal("1.0168")
    adpa = df.filter(pl.col("ticker") == "ADPA21").row(0, named=True)  # `--` is a null; Reune 5
    assert adpa["bid_rate_pct"] is None and adpa["reune_pct"] == Decimal("5")
    assert set(df["indexer"]) == {"DI", "IPCA", "IGP-M", "PRE"} and df["percent_of_di"].null_count() < df.height
    assert df.filter(pl.col("ticker") == "AEGE16")["name_marks"][0] == "(*) (**)"
    assert df.filter(pl.col("ticker") == "AERI11")["duration_bdays"][0] is None  # `N/D`


def test_debentures_need_the_manifest_date() -> None:
    with pytest.raises(ap.LayoutError):
        ap.parse_debentures((FIX / "anbima_debentures" / "db261106.txt").read_bytes(), _row("db_txt"))


def test_titulos_publicos() -> None:
    blob = (FIX / "anbima_titulos_publicos" / "ms261106.txt").read_bytes()
    df = _clean(ap.parse_titulos(blob, _row("ms_txt")), ap.BOND_RATE)
    assert df.height == 50 and set(df["ref_date"]) == {date(2026, 11, 6)}
    ltn = df.filter((pl.col("bond_type") == "LTN") & (pl.col("maturity_date") == date(2027, 4, 1))).row(0, named=True)
    assert ltn["indicative_rate_pct"] == Decimal("13.7549") and ltn["price_brl"] == Decimal("951.116782")
    assert ltn["issue_date"] == date(2025, 1, 10) and ltn["criterion"] == "Calculado"
    assert ltn["std_dev"] == Decimal("0.00558174106619") and ltn["upper_d1_pct"] == Decimal("14.0069")


def test_titulos_xls_is_archived_not_parsed() -> None:
    xls = (FIX / "anbima_titulos_publicos" / "m26nov06.xls").read_bytes()
    assert list(ap.parse_titulos_payload(xls, _row("ms_xls"))) == []
    (p,) = ap.parse_titulos_payload((FIX / "anbima_titulos_publicos" / "ms261106.txt").read_bytes(), _row("ms_txt"))
    assert p.partition == "ref_date=2026-11-06"


def test_quadro_indicadores() -> None:
    blob = (FIX / "anbima_projecoes" / "quadro_indicadores_2026-11-06_1818.html").read_bytes()
    df = _clean(ap.parse_indicators(blob, _row("quadro_indicadores")), ap.INDICATOR)
    assert df.height == 17 and set(df["updated_at"]) == {datetime(2026, 11, 6, 18, 18)}

    def one(code: str) -> dict[str, Any]:
        d = df.filter(pl.col("indicator") == code)
        assert d.height == 1
        return d.row(0, named=True)

    assert one("igpm_index")["value"] == Decimal("1243.905") and one("igpm_index")["period"] == "out/26"
    assert one("igpm_projection")["value"] == Decimal("0.87") and one("igpm_projection")["period"] == "nov/26"
    assert one("ipca_index")["value"] == Decimal("7695.82") and one("ipca_projection")["period"] == "out/26"
    assert one("usd_sell")["value"] == Decimal("5.5013") and one("usd_sell")["observation_date"] == date(2026, 11, 6)
    assert one("selic_bcb")["value"] == Decimal("13.65") and one("tr")["observation_date"] == date(2026, 11, 5)
    assert df.filter(pl.col("indicator") == "fds_quota").height == 2


def test_quadro_without_timestamp_is_not_data() -> None:
    with pytest.raises(NotData):
        ap.parse_indicators(b"<html><body>manutencao</body></html>", _row("quadro_indicadores"))


def _ettj_file(*parts: str) -> dict[str, pl.DataFrame]:
    frames = ap.parse_ettj((FIX.joinpath(*parts)).read_bytes(), _row("curva_zero_mensal"))
    return {k: _clean(v, ap.ETTJ_CONTRACTS[k]) for k, v in frames.items()}


def test_susep_english_copy_equals_anbima_pt_file_of_the_same_day() -> None:
    """SUSEP's month-end copy (English labels, `1,008.5` numbers) parses to ANBIMA's own PT file of 2026-10-30."""
    en, pt = _ettj_file("susep_ettj", "CurvaZero_202610.txt"), _ettj_file("anbima_ettj", "CurvaZero_30102026.txt")
    assert en.keys() == pt.keys()
    for k in en:
        cols = [c for c in en[k].columns if c not in ("raw_sha256", "ingest_run_id", "raw_locator")]
        assert en[k].select(cols).equals(pt[k].select(cols)), k
    assert en["parameter"]["ref_date"].unique().to_list() == [date(2026, 10, 30)]
    assert en["vertex"].filter(pl.col("business_days") == 1008).height == 1  # `1,008` is thousands


def test_susep_first_month_2015_12() -> None:
    f = _ettj_file("susep_ettj", "CurvaZero_201512.txt")
    assert f["parameter"]["ref_date"].unique().to_list() == [date(2015, 12, 31)]
    assert f["parameter"].filter(pl.col("curve") == "PREFIXADOS").row(0, named=True)["beta1"] == Decimal(
        "0.184887270885752"
    )
    assert f["vertex"].height > 60 and f["bond_error"].height > 20


def test_susep_bond_maturity_order_is_read_from_the_dates() -> None:
    """Of 131 SUSEP files one (2025-12-30) writes maturities dd/mm/yyyy, the others mm/dd/yyyy; none may be guessed."""
    dec = _ettj_file("susep_ettj", "CurvaZero_202512.txt")["bond_error"]
    assert dec.filter(pl.col("bond_type") == "NTN-B")["maturity_date"].dt.day().unique().to_list() == [15]
    assert dec.filter(pl.col("bond_type") == "LTN")["maturity_date"].dt.day().unique().to_list() == [1]
    oct26 = _ettj_file("susep_ettj", "CurvaZero_202610.txt")["bond_error"]
    assert oct26.filter(pl.col("bond_type") == "NTN-B")["maturity_date"].dt.day().unique().to_list() == [15]
    blob = (FIX / "susep_ettj" / "CurvaZero_202610.txt").read_bytes()
    only_ltn = b"\r\n".join(ln for ln in blob.split(b"\r\n") if not ln.startswith((b"4@NTN", b"4@LFT")))
    with pytest.raises(ap.LayoutError, match="do not settle"):
        ap.parse_ettj(only_ltn, _row("curva_zero_mensal"))
