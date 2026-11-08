"""SND debenture terms and trade statistics: layouts from real files, exact decimals, drift refused, and the core
`debenture` table (ADR-0028)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import polars as pl
import pytest

from fin.config import Zones
from fin.core import debentures
from fin.ingest import snd
from fin.ingest.base import NotData
from fin.store.manifest import ManifestRow
from fin.store.runs import IngestRun
from fin.store.tables import write_parquet

FIX = Path(__file__).parents[1] / "fixtures" / "snd_debentures"


def _row(sha: str = "a" * 64) -> dict[str, Any]:
    return {"raw_sha256": sha, "ingest_run_id": "r"}


def _terms() -> pl.DataFrame:
    (p,) = list(snd.parse_terms((FIX / "caracteristicas_sample.txt").read_bytes(), _row()))
    assert p.dataset_id == "caracteristicas"
    good, bad = snd.TERMS.split(p.frame)
    assert bad.height == 0
    return good


def test_terms_parse_exactly() -> None:
    df = _terms()
    assert df.height == 7
    a = df.filter(pl.col("ticker") == "AAJR11").row(0, named=True)
    assert a["isin"] == "BRAAJRDBS002" and a["issuer_cnpj"] == "31907982000123"
    assert (a["issue_date"], a["maturity_date"]) == (date(2025, 6, 23), date(2029, 6, 27))
    assert (a["indexer"], a["index_percent"], a["coupon_rate"]) == ("DI", Decimal("100"), Decimal("3.5"))
    assert a["nominal_at_issue"] == Decimal("1000") and a["nominal_current"] == Decimal("800")
    assert a["qty_issued"] == 100000 and a["qty_market"] == 100000
    assert a["situation"] == "Registrado" and a["incentivised"] == "N"
    assert a["next_repactuation_date"] is None  # "-" is no value
    assert df.filter(pl.col("ticker") == "BESC11").height == 2  # one row per co-issuer
    assert df.filter(pl.col("ticker") == "ZZDT11")["situation"][0] == "Excluído"


def test_terms_layout_drift_raises() -> None:
    blob = (FIX / "caracteristicas_sample.txt").read_bytes().replace(b"Serie\t", b"Series\t", 1)
    with pytest.raises(snd.LayoutError):
        list(snd.parse_terms(blob, _row()))
    with pytest.raises(NotData):
        list(snd.parse_terms(b"<html>erro</html>", _row()))


def _prices(name: str) -> list[Any]:
    return list(snd.parse_prices((FIX / name).read_bytes(), _row()))


def test_prices_parse_exactly() -> None:
    (p,) = _prices("precos_1993-11.txt")
    assert p.partition == "year=1993"
    good, bad = snd.SECONDARY_PRICE.split(p.frame)
    assert bad.height == 0 and good.height == 5
    d = good.filter(pl.col("trade_date") == date(1993, 11, 1)).row(0, named=True)
    assert d["ticker"] == "ILAM14" and d["isin"] == "BRCILSDBS013" and d["quantity"] == Decimal("6100")
    assert d["n_trades"] is None and d["pct_of_curve_pu"] is None  # "-" and "ND"
    assert (d["pu_min_brl"], d["pu_avg_brl"], d["pu_max_brl"]) == (
        Decimal("13.68"),
        Decimal("136215.62"),
        Decimal("138028.79"),
    )
    (q,) = _prices("precos_2010-03_head.txt")
    r = q.frame.filter(pl.col("ticker") == "AMRO15").row(0, named=True)
    assert r["trade_date"] == date(2010, 3, 31) and r["n_trades"] == 1 and r["pct_of_curve_pu"] == Decimal("100")
    assert q.frame.filter(pl.col("ticker") == "CVRDA6")["pct_of_curve_pu"][0] is None


def test_prices_empty_answer_and_drift() -> None:
    assert _prices("precos_empty_1993-12.txt") == []
    blob = (FIX / "precos_1993-11.txt").read_bytes().replace("Número de Negócios".encode("latin-1"), b"Negocios")
    with pytest.raises(snd.LayoutError):
        list(snd.parse_prices(blob, _row()))


def test_isin_check_digit() -> None:
    assert debentures.isin_valid("BRAAJRDBS002")
    assert not debentures.isin_valid("000000000000") and not debentures.isin_valid(None)
    assert not debentures.isin_valid("BRKANTDBS999")  # a placeholder shared by 40 codes


def test_debenture_core(zones: Zones) -> None:
    terms = _terms()
    with IngestRun(zones, "test") as run:
        write_parquet(terms, zones.staging / "snd_debentures" / "caracteristicas" / "all" / f"{'a' * 64}.parquet")
        run.manifest.append(
            ManifestRow(
                "a" * 64, "txt", "snd_debentures", "caracteristicas", "{}", "k", datetime(2026, 11, 8, tzinfo=UTC),
                200, None, 1, None, None, date(2026, 11, 8), run.run_id, "1",
            )
        )  # fmt: skip
        issuer = pl.DataFrame({"issuer_id": ["C1"], "cnpj": ["31907982000123"]})
        write_parquet(issuer, zones.core / "issuer" / "issuer.parquet")
        out = debentures.build(zones, run)
    assert out["debenture"] == 6 and out["co_issued"] == 1 and out["with_issuer_id"] == 1  # 7 rows, BESC11 twice
    d = pl.read_parquet(zones.core / "debenture" / "debenture.parquet")
    a = d.filter(pl.col("ticker") == "AAJR11").row(0, named=True)
    assert a["debenture_id"] == debentures.debenture_id("AAJR11") and a["issuer_id"] == "C1"
    assert a["isin"] == "BRAAJRDBS002" and a["isin_shared_by"] == 1 and a["incentivised"] is False
    z = d.filter(pl.col("ticker") == "ZZDT11").row(0, named=True)
    assert z["situation"] == "Excluído" and z["exit_date"] is not None
    b = d.filter(pl.col("ticker") == "BESC11").row(0, named=True)
    assert len(b["co_issuer_cnpjs"]) == 1
    assert d.filter(pl.col("isin").is_null()).height >= 2  # placeholder and blank ISINs are not identities
    assert d["debenture_id"].n_unique() == d.height
