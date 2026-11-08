"""The CVM register parses without its contact fields; one issuer per CNPJ with all its CVM codes."""

from __future__ import annotations

from pathlib import Path

from fin.config import Zones
from fin.core import issuers
from fin.store.tables import write_parquet

FIX = Path(__file__).parents[1] / "fixtures" / "cvm_cia_cadastro" / "cad_cia_aberta.csv"
ROW = {"raw_sha256": "a" * 64, "ingest_run_id": "r", "dataset_id": "cad_cia_aberta"}


def test_register_drops_personal_contact_fields() -> None:
    df = issuers.parse_register(FIX.read_bytes(), ROW)
    good, bad = issuers.COMPANY.split(df)
    assert bad.height == 0 and good.height > 0
    assert not {"RESP", "EMAIL_RESP", "TEL_RESP", "resp", "email"} & set(good.columns)


def test_one_issuer_per_cnpj_with_every_cvm_code(zones: Zones) -> None:
    df = issuers.COMPANY.split(issuers.parse_register(FIX.read_bytes(), ROW))[0]
    write_parquet(df, zones.staging / "cvm_cia_cadastro" / "company" / "all" / "a.parquet")
    issuers.build(zones)
    import polars as pl

    out = pl.read_parquet(zones.core / "issuer" / "issuer.parquet")
    itau = out.filter(pl.col("cnpj") == "60872504000123").row(0, named=True)
    # Itaú: code 1279 (cancelled 1998) and 19348 (active since 2002), newest registration first (source note §4)
    assert itau["cd_cvm"].split(",")[0] == "19348" and "1279" in itau["cd_cvm"]
    assert itau["issuer_id"] == issuers.issuer_id("60872504000123") and out["cnpj"].n_unique() == out.height


def test_an_isin_belongs_to_the_fund_with_a_majority_of_its_reports() -> None:
    import polars as pl

    from fin.core.issuers import isin_owners

    p = pl.DataFrame({
        "isin": ["BRBBPOCTF003"] * 9 + ["BRXXXXCTF000"] * 4,
        "cnpj": ["A"] * 6 + ["B"] * 2 + ["C"] + ["D", "D", "E", "E"],
    })  # fmt: skip
    own = isin_owners(p)
    assert own.select("isin", "cnpj").rows() == [("BRBBPOCTF003", "A")]  # a 2-2 tie has no owner


def test_name_history_needs_both_the_short_name_and_the_isin_code() -> None:
    from fin.core.issuers import _name_match, _tokens

    assert _name_match("KROTON EDUCACIONAL S.A.", _tokens("KROTON"), "KROT")
    assert _name_match("CETIP S.A. - MERCADOS ORGANIZADOS", _tokens("CETIP"), "CTIP")
    assert _name_match("TRACTEBEL ENERGIA S.A.", _tokens("TRACTEBEL"), "TBLE")
    assert not _name_match("SUNO FIAGRO", _tokens("CAF BRASILIA"), "CAFB")  # a reassigned code: the words disagree
    # the known weakness, why the method comes last and never overrides another: a similar name can pass
    assert _name_match("SABER SERVICOS EDUCACIONAIS S.A.", _tokens("SER EDUCA"), "SEER")
