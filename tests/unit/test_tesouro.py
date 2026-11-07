"""Tesouro Direto's price/rate CSV parses to exact decimals; a 0,00 PU is 'not offered', a zero base PU quarantines."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from fin.ingest import tesouro

FIX = Path(__file__).parents[1] / "fixtures" / "tesouro_transparente"
ROW = {"raw_sha256": "a" * 64, "ingest_run_id": "run-1"}


def test_fixture_parses_exactly() -> None:
    df = tesouro.parse_price_rate((FIX / "PrecoTaxaTesouroDireto_cut.csv").read_bytes(), ROW)
    good, bad = tesouro.PRICE_RATE.split(df)
    assert (good.height, bad.height) == (7252, 0)
    r = good.row(2, named=True)
    assert (r["title"], r["maturity"], r["base_date"]) == (
        "Tesouro IPCA+ com Juros Semestrais",
        date(2035, 5, 15),
        date(2026, 11, 5),
    )
    assert (r["buy_rate"], r["buy_pu"], r["base_pu"]) == (Decimal("7.91"), Decimal("4381.57"), Decimal("4348.72"))
    assert r["raw_locator"] == "line=4"


def test_zero_pu_is_not_offered_and_zero_base_quarantines() -> None:
    head = ";".join(tesouro.HEADER)
    rows = [
        "Tesouro Prefixado com Juros Semestrais;01/01/2023;29/12/2022;9,50;9,62;0,00;1047,70;1047,70",
        "Tesouro Selic;01/03/2027;05/11/2026;0,02;0,03;20240,75;20229,76;0,00",
    ]
    df = tesouro.parse_price_rate(("\n".join([head, *rows]) + "\n").encode(), ROW)
    good, bad = tesouro.PRICE_RATE.split(df)
    assert good["buy_pu"].to_list() == [None] and good["sell_pu"].to_list() == [Decimal("1047.70")]
    assert bad["reject_rules"].to_list() == [["base_pu_positive"]]


def test_changed_header_is_refused() -> None:
    with pytest.raises(tesouro.LayoutError):
        tesouro.parse_price_rate(b"Tipo;Data\nx;y\n", ROW)
