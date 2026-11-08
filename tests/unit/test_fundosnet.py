"""Fundos.NET notices parse to one row per (Provento, kind) with exact values; personal contact fields are not
parsed; a misfiled monthly report is not data; the listing gives the delivery minute in UTC."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from fin.ingest import fundosnet
from fin.ingest.base import NotData

FIX = Path(__file__).parents[1] / "fixtures" / "b3_fundosnet"


def _row(doc_id: int, dataset: str = "informe_rendimentos") -> dict[str, Any]:
    url = "https://fnet.bmfbovespa.com.br/fnet/publico/downloadDocumento"
    return {
        "raw_sha256": "a" * 64,
        "ingest_run_id": "run-1",
        "dataset_id": dataset,
        "request": json.dumps({"url": url, "params": {"id": doc_id}}),
    }


def _parse(doc_id: int, name: str | None = None) -> Any:
    blob = (FIX / (name or f"doc_{doc_id}.xml")).read_bytes()
    good, bad = fundosnet.DISTRIBUTION.split(fundosnet.parse_distribution(blob, _row(doc_id)))
    assert bad.height == 0
    return good


def test_income_notice() -> None:
    r = _parse(1371379).row(0, named=True)
    assert (r["trading_code"], r["kind"], r["base_date"], r["payment_date"]) == (
        "TINF11",
        "rendimento",
        date(2026, 11, 6),
        date(2026, 11, 13),
    )
    assert r["value_per_quota"] == Decimal("0.4") and r["tax_exempt"] is True and r["doc_id"] == 1371379
    assert "ResponsavelInformacao" not in str(fundosnet.DISTRIBUTION.names)


def test_both_kinds_keep_every_decimal() -> None:
    df = _parse(485737)
    assert df["kind"].to_list() == ["rendimento", "amortizacao"]
    assert df["value_per_quota"].to_list() == [Decimal("1.8520708248596"), Decimal("7.74067951564453")]
    assert df["amortization_type"].to_list() == [None, "Parcial"] and df["tax_exempt"].to_list() == [True, None]


def test_total_amortization() -> None:
    assert "Total" in _parse(496707)["amortization_type"].to_list()


def test_monthly_report_filed_as_notice_is_not_data() -> None:
    with pytest.raises(NotData):
        fundosnet.parse_distribution((FIX / "doc_991793_informe_mensal.xml").read_bytes(), _row(991793))


def test_value_past_scale_is_refused() -> None:
    blob = (FIX / "doc_1371379.xml").read_bytes().replace(b">0.4<", b">0.40000000000000000000001<")  # 23 decimals
    assert b"0.40000000000000000000001" in blob
    with pytest.raises(fundosnet.LayoutError):
        fundosnet.parse_distribution(blob, _row(1371379))


def test_listing_gives_delivery_minute_in_utc() -> None:
    df = fundosnet.parse_listing((FIX / "listagem_offset0.json").read_bytes(), _row(0, "listagem"))
    good, bad = fundosnet.LISTING.split(df)
    assert (good.height, bad.height) == (200, 0)
    first = good.row(0, named=True)
    assert first["doc_id"] == 1371379 and first["delivered_at"] == datetime(2026, 11, 6, 21, 8, tzinfo=UTC)


def test_old_layout_without_provento() -> None:
    # notices before 2022: Rendimento/Amortizacao directly under InformeRendimentos, ISIN in DadosGerais
    blob = b"""<?xml version="1.0" encoding="UTF-8"?><DadosEconomicoFinanceiros><DadosGerais>
<NomeFundo>F</NomeFundo><CNPJFundo>13842683000176</CNPJFundo><CNPJAdministrador>00806535000154</CNPJAdministrador>
<CodISINCota>BRVLJSCTF020</CodISINCota><CodNegociacaoCota>VLJS11</CodNegociacaoCota></DadosGerais>
<InformeRendimentos><Rendimento></Rendimento><Amortizacao tipo="Parcial"><DataAprovacao>2022-11-10</DataAprovacao>
<DataBase>2022-11-10</DataBase><DataPagamento>2022-11-21</DataPagamento>
<ValorProventoCota>23.9888159102366</ValorProventoCota><PeriodoReferencia>NOVEMBRO</PeriodoReferencia>
</Amortizacao></InformeRendimentos></DadosEconomicoFinanceiros>"""
    df = fundosnet.parse_distribution(blob, _row(374888))
    assert df.select("isin", "trading_code", "kind", "amortization_type").rows() == [
        ("BRVLJSCTF020", "VLJS11", "amortizacao", "Parcial")
    ]
    assert str(df["value_per_quota"][0]).startswith("23.9888159102366")


def test_formatted_cnpj_and_malformed_isin_are_kept() -> None:
    # 27 notices write the CNPJ formatted; some write an ISIN like "0": kept (core maps it by trading code)
    blob = b"""<?xml version="1.0" encoding="UTF-8"?><DadosEconomicoFinanceiros><DadosGerais>
<NomeFundo>F</NomeFundo><CNPJFundo>17.007.443/0001-07</CNPJFundo><CNPJAdministrador>00806535000154</CNPJAdministrador>
<CodISINCota>0</CodISINCota><CodNegociacaoCota>ABCD11</CodNegociacaoCota></DadosGerais>
<InformeRendimentos><Rendimento><DataBase>2020-12-30</DataBase><DataPagamento>2020-01-15</DataPagamento>
<ValorProventoCota>0.5</ValorProventoCota></Rendimento></InformeRendimentos></DadosEconomicoFinanceiros>"""
    df = fundosnet.parse_distribution(blob, _row(1))
    good, bad = fundosnet.DISTRIBUTION.split(df)
    assert bad.height == 0 and good["fund_cnpj"][0] == "17007443000107" and good["isin"][0] == "0"
