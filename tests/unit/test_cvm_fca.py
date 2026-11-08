"""FCA index, geral and valor_mobiliario parse from the committed real lines; contact members are skipped."""

from __future__ import annotations

import io
import zipfile
from datetime import date
from pathlib import Path

import pytest

from fin.ingest import cvm_fca

FIX = Path(__file__).parents[1] / "fixtures" / "cvm_fca"
ROW = {"raw_sha256": "a" * 64, "ingest_run_id": "r", "notes": "2026"}


def _zip(*names: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n in names:
            z.writestr(n, (FIX / n).read_bytes())
    return buf.getvalue()


def test_index_geral_and_securities() -> None:
    names = ("fca_cia_aberta_2026.csv", "fca_cia_aberta_geral_2026.csv", "fca_cia_aberta_valor_mobiliario_2026.csv")
    out = {p.dataset_id: p.frame for p in cvm_fca.parse_payload(_zip(*names), ROW)}
    assert set(out) == {"document", "company", "security"}
    for ds, frame in out.items():
        assert cvm_fca.CONTRACTS[ds].split(frame)[1].height == 0
    sec = out["security"]
    petr4 = sec.filter(sec["trading_code"] == "PETR4").row(0, named=True)
    assert petr4["cnpj"] == "33.000.167/0001-01" and petr4["market"] == "Bolsa"
    assert petr4["security_type"] == "Ações Preferenciais" and petr4["listing_segment"].startswith("Nível 2")
    brf = sec.filter(sec["trading_code"] == "BRFS3").row(0, named=True)
    assert brf["trading_end"] == date(2025, 9, 22) and brf["trading_start"] == date(2006, 2, 17)
    co = out["company"]
    assert "pagina_web" not in co.columns and "web_page" not in co.columns
    petro = co.filter(co["cnpj"] == "33.000.167/0001-01").row(0, named=True)
    assert petro["cvm_code"] == "009512" and petro["fiscal_year_end_month"] == 12
    assert out["document"]["received_on"].null_count() == 0


def test_old_year_and_skipped_member() -> None:
    blob = _zip("fca_cia_aberta_valor_mobiliario_2010.csv")
    out = list(cvm_fca.parse_payload(blob, ROW | {"notes": "2010"}))
    assert [p.dataset_id for p in out] == ["security"] and out[0].partition == "year=2010"
    assert out[0].frame["trading_code"].null_count() == out[0].frame.height  # no tickers in 2010
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("fca_cia_aberta_endereco_2026.csv", b"x;y\r\n")
    assert list(cvm_fca.parse_payload(buf.getvalue(), ROW)) == []


def test_header_change_raises() -> None:
    data = (FIX / "fca_cia_aberta_valor_mobiliario_2026.csv").read_bytes().replace(b"Segmento", b"Segmentox", 1)
    with pytest.raises(cvm_fca.LayoutError):
        cvm_fca.parse_member(data, "m.csv", cvm_fca.VALOR, ROW)
