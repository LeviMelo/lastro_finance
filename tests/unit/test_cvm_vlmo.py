"""CVM VLMO: index and movements parse to their contracts with exact values; free text is never read."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import polars as pl
import pytest

from fin.ingest import cvm_vlmo as v

FIX = Path(__file__).parents[1] / "fixtures" / "cvm_vlmo"
ROW = {"raw_sha256": "x", "ingest_run_id": "r"}


def test_index_carries_the_delivery_date_and_no_free_text() -> None:
    df = v.parse_member((FIX / "vlmo_cia_aberta_2025.csv").read_bytes(), "vlmo_cia_aberta_2025.csv", v.INDEX, ROW)
    good, bad = v.DOCUMENT.split(df)
    assert bad.height == 0 and good.height == 41
    r = good.row(0, named=True)
    assert (r["company_cnpj"], r["reference_month"], r["version"]) == ("01838723000127", date(2025, 1, 1), 1)
    assert r["delivered_on"] == date(2025, 2, 10) and r["cd_cvm"] == "16292"
    assert "Motivo_Reapresentacao" not in df.columns and "reason" not in df.columns


def test_movements_are_exact_and_signed() -> None:
    name = "vlmo_cia_aberta_con_2025.csv"
    df = v.parse_member((FIX / name).read_bytes(), name, v.MOVEMENT_COLS, ROW)
    good, bad = v.MOVEMENT.split(df)
    assert bad.height == 0 and good.height == 1200
    sale = good.filter((pl.col("company_cnpj") == "60872504000123") & (pl.col("movement_date") == date(2025, 3, 5)))
    r = sale.row(0, named=True)
    assert r["role_group"] == "Controlador ou Vinculado" and r["direction"] == "Débito" and r["quantity"] == 3600
    assert r["unit_price_brl"] == Decimal("32.4") and r["volume_brl"] == Decimal("116640")
    assert not any("descri" in c for c in df.columns)


def test_a_changed_header_fails_loudly() -> None:
    with pytest.raises(v.LayoutError):
        v.parse_member(b"A;B\r\n1;2\r\n", "vlmo_cia_aberta_2025.csv", v.INDEX, ROW)
