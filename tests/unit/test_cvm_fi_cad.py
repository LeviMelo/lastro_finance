"""CVM fund register parsers from committed real lines (tests/fixtures/cvm_fi_cadastro; Diretor blanked)."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import polars as pl
import pytest

from fin.ingest import cvm_fi_cad
from fin.ingest.cvm_fi_cad import LayoutError

FIX = Path(__file__).parents[1] / "fixtures" / "cvm_fi_cadastro"
ROW = {"raw_sha256": "a" * 64, "ingest_run_id": "r", "notes": None, "dataset_id": "registro_fundo_classe"}


def _zip(*names: str, patch: dict[str, bytes] | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n in names:
            z.writestr(n, (patch or {}).get(n, (FIX / n).read_bytes()))
    return buf.getvalue()


def _parse(blob: bytes, dataset_id: str) -> dict[str, pl.DataFrame]:
    out = {p.dataset_id: p.frame for p in cvm_fi_cad.parse_payload(blob, {**ROW, "dataset_id": dataset_id})}
    for ds, frame in out.items():
        assert cvm_fi_cad.CONTRACTS[ds].split(frame)[1].height == 0, ds
    return out


def test_registro_zip_gives_fund_class_subclass() -> None:
    out = _parse(_zip("registro_fundo.csv", "registro_classe.csv", "registro_subclasse.csv"), "registro_fundo_classe")
    assert set(out) == {"registered_fund", "registered_class", "registered_subclass"}
    fund = out["registered_fund"].filter(pl.col("fund_id") == "28272").row(0, named=True)
    assert fund["cnpj"] == "01597187000115" and str(fund["adapted_on"]) == "2024-08-29"
    assert fund["manager_cnpj"] == "40430971000196" and str(fund["net_assets_brl"]) == "115226871477.48"
    cls = out["registered_class"].filter(pl.col("class_id") == "142").row(0, named=True)
    assert cls["fund_id"] == "28272" and cls["cnpj"] == "01597187000115"
    assert out["registered_class"].height == 6 and out["registered_subclass"].height == 5
    assert "raw_locator" in out["registered_class"].columns


def test_no_person_is_parsed() -> None:
    assert not any("diretor" in c.src.lower() for c in cvm_fi_cad.REGISTERED_FUND + cvm_fi_cad.FUND)
    line = (FIX / "registro_fundo.csv").read_bytes()
    pj = b"PJ;40430971000196;ITAU UNIBANCO ASSET MANAGEMENT LTDA"
    assert pj in line
    pf = line.replace(pj, b"PF;12345678901;SOMEONE")  # a person-type manager: name and CPF are dropped
    out = _parse(_zip("registro_fundo.csv", patch={"registro_fundo.csv": pf}), "registro_fundo_classe")
    row = out["registered_fund"].filter(pl.col("fund_id") == "28272").row(0, named=True)
    assert row["manager_person_type"] == "PF" and row["manager"] is None and row["manager_cnpj"] is None


def test_cad_fi_legacy_row() -> None:
    out = _parse((FIX / "cad_fi.csv").read_bytes(), "cad_fi")
    row = out["fund"].row(0, named=True)
    assert row["cnpj"] == "01597187000115" and row["status"] == "CANCELADA" and row["cd_cvm"] == "9016"
    assert str(row["cancelled_on"]) == "2005-03-07" and str(row["net_assets_brl"]) == "3975246455.90"
    assert row["manager"] is None and row["administrator"] is None


def test_history_is_long_form_with_company_cnpj() -> None:
    names = ["cad_fi_hist_sit.csv", "cad_fi_hist_denom_social.csv", "cad_fi_hist_admin.csv", "cad_fi_hist_classe.csv"]
    h = _parse(_zip(*names), "cad_fi_hist")["fund_history"]
    assert set(h["attribute"]) == {"status", "name", "administrator", "category"}
    adm = h.filter(pl.col("attribute") == "administrator")
    assert adm["value_cnpj"].null_count() == 0 and adm["value_cnpj"].str.len_chars().eq(14).all()
    sit = h.filter((pl.col("attribute") == "status") & (pl.col("cnpj") == "01597187000115"))
    assert sit.height >= 1 and sit["valid_to"].null_count() <= 1  # at most the current status is open


def test_header_change_is_loud_and_meta_is_ignored() -> None:
    bad = (FIX / "cad_fi_hist_sit.csv").read_bytes().replace(b"DT_FIM_SIT", b"DT_END_SIT")
    with pytest.raises(LayoutError):
        list(cvm_fi_cad.parse_payload(_zip("cad_fi_hist_sit.csv", patch={"cad_fi_hist_sit.csv": bad}), ROW))
    meta = io.BytesIO()
    with zipfile.ZipFile(meta, "w") as z:
        z.writestr("meta_registro_fundo.txt", b"Campo: X")
    assert list(cvm_fi_cad.parse_payload(meta.getvalue(), ROW)) == []
