"""Fundos.NET ETF month-end portfolios: legacy and urn:cda layouts parse to one contract, values exact."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import polars as pl
import pytest

from fin.ingest import fundosnet_cda as fc
from fin.ingest.base import NotData

FIX = Path(__file__).parents[1] / "fixtures" / "b3_fundosnet_cda"


def _row(doc_id: int) -> dict:
    return {"raw_sha256": "x", "ingest_run_id": "r", "dataset_id": "carteira",
            "request": json.dumps({"params": {"id": doc_id}})}  # fmt: skip


def _parse(name: str, doc_id: int, blob: bytes | None = None) -> tuple[pl.DataFrame, pl.DataFrame]:
    pos, net = fc.parse_cda(blob if blob is not None else (FIX / name).read_bytes(), _row(doc_id))
    for contract, df in ((fc.POSITION, pos), (fc.NET_ASSETS, net)):
        good, bad = contract.split(df)
        assert bad.height == 0 and good.height == df.height
    return pos, net


def test_legacy_layout() -> None:
    pos, net = _parse("cda_33547_2018_legacy.xml", 33547)
    assert pos.height == 72
    n = net.row(0, named=True)
    assert (n["fund_cnpj"], n["reference_month"], n["layout"]) == ("13416245000146", date(2018, 9, 1), "legacy")
    assert n["net_assets_brl"] == Decimal("57700173.75") and n["generated_on"] == date(2018, 10, 4)
    r = pos.row(0, named=True)
    assert (r["asset_type_text"], r["asset_code"], r["block"]) == ("Títulos Públicos", "210100", "APLICACAO")
    assert r["sold_qty"] == Decimal(19) and r["bought_brl"] == Decimal("213177.43")
    assert r["market_value_brl"] == Decimal("29188.68") and r["net_assets_percent"] == Decimal("0.050587")
    assert r["cost_value_brl"] is None and r["raw_locator"] == "Carteira/Aplicacoes/Aplicacao[1]"


def test_cda_layout_with_public_bonds_and_other_assets() -> None:
    pos, net = _parse("cda_1306695_2026.xml", 1306695)
    assert net.row(0, named=True)["net_assets_brl"] == Decimal("4314903828.92")
    assert dict(pos.group_by("block").len().iter_rows()) == {"TIT_PUB": 10, "DEMAIS_N_CODIF": 2}
    r = pos.row(1, named=True)
    assert (r["selic_code"], r["maturity_date"], r["position_type_code"]) == ("210100", date(2030, 12, 1), "75")
    assert r["final_qty"] == Decimal(27371) and r["market_value_brl"] == Decimal("539686055.30")
    assert r["sold_qty"] == Decimal(4546) and r["bought_brl"] == Decimal("570598.24")
    last = pos.row(-1, named=True)
    assert last["asset_description"] == "VALORES A RECEBER" and last["market_value_brl"] == Decimal("60468.94")
    assert last["final_qty"] is None and last["raw_locator"].endswith("/DEMAIS_N_CODIF[12]")


def test_quota_line_and_empty_negoc() -> None:
    pos, net = _parse("cda_1371722_2026.xml", 1371722)
    assert net.row(0, named=True)["net_assets_brl"] == Decimal(0)
    r = pos.row(0, named=True)
    assert (r["block"], r["held_fund_cnpj"], r["related_issuer"]) == ("COTAS", "36771728000164", "S")
    assert r["sold_qty"] is None and r["final_qty"] == Decimal(0) and r["reference_month"] == date(2026, 9, 1)


def test_utf8_body_declared_windows_1252_and_short_cnpj() -> None:
    pos, _ = _parse("cda_1240750_2026.xml", 1240750)
    quota = pos.filter(pl.col("block") == "COTAS").row(0, named=True)
    assert quota["held_fund_cnpj"] == "06175696000173"  # the source wrote 6175696000173
    assert quota["final_qty"] == Decimal("786.498108")
    abroad = pos.filter(pl.col("block") == "INV_EXT").row(0, named=True)
    assert (abroad["issuer_name"], abroad["country_code"], abroad["exchange_code"]) == ("XPINVESTIMEN", "28", "99")
    assert abroad["maturity_date"] == date(2050, 12, 31) and abroad["confidential_days"] == 90
    assert any("BANCÁRIAS" in (d or "") for d in pos["asset_description"])


def test_agro_credit_and_equities() -> None:
    pos, _ = _parse("cda_1211835_2026.xml", 1211835)
    a = pos.filter(pl.col("block") == "TIT_AGRO_CRED_PRIV").row(0, named=True)
    assert (a["issuer_tax_id"], a["issuer_name"], a["index_code"]) == ("02773542000122", "OPEA", "OUT")
    assert a["coupon_percent"] == Decimal("4.232250") and a["index_percent"] == Decimal(100)
    assert a["bought_qty"] == Decimal(10430) and a["is_postfixed"] == "S" and a["has_guarantee"] == "N"
    assert dict(pos.group_by("block").len().iter_rows())["DEMAIS_CODIF"] == 4


def test_natural_person_issuer_is_dropped() -> None:
    xml = (FIX / "cda_1211835_2026.xml").read_bytes().decode("utf-8")
    xml = xml.replace("02773542000122", "21345218800", 1)
    xml = xml.replace("<NM_EMIS>OPEA</NM_EMIS>", "<NM_EMIS>FULANO DE TAL</NM_EMIS>", 1)
    pos, _ = _parse("", 1211835, xml.encode("utf-8"))
    a = pos.filter(pl.col("block") == "TIT_AGRO_CRED_PRIV").row(0, named=True)
    assert a["issuer_tax_id"] is None and a["issuer_name"] is None and a["final_qty"] == Decimal(10430)


def test_unknown_element_and_block_fail_loudly() -> None:
    xml = (FIX / "cda_1371722_2026.xml").read_bytes().decode("cp1252")
    with pytest.raises(fc.LayoutError, match="NOVO"):
        fc.parse_cda(xml.replace("<EMPR_LIGADA>", "<NOVO>1</NOVO><EMPR_LIGADA>").encode(), _row(1))
    with pytest.raises(fc.LayoutError, match="asset block"):
        fc.parse_cda(xml.replace("COTAS>", "SWAP>").encode(), _row(1))
    with pytest.raises(fc.LayoutError, match="decimals"):
        fc.parse_cda(xml.replace("<MERC_POS_FIM>0,00", "<MERC_POS_FIM>0,00001").encode(), _row(1))


def test_not_data_bodies() -> None:
    with pytest.raises(NotData):
        fc.parse_cda(b"Ocorreu um enviar o arquivo XML.", _row(35023))
    fidc = b'<?xml version="1.0"?><DOC_ARQ><CAB_INFORM/><LISTA_INFORM><APLIC_ATIVO/></LISTA_INFORM></DOC_ARQ>'
    with pytest.raises(NotData):
        fc.parse_cda(fidc, _row(616210))


def test_parse_payload_datasets() -> None:
    out = list(fc.parse_payload((FIX / "cda_1371722_2026.xml").read_bytes(), _row(1371722)))
    assert [(p.dataset_id, p.partition) for p in out] == [("position", "id_block=13"), ("net_assets", "id_block=13")]
    with pytest.raises(fc.LayoutError):
        list(fc.parse_payload(b"", _row(1) | {"dataset_id": "x"}))
