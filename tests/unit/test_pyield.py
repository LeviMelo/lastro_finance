"""The pyield mirror's floats become Decimals at the primary's precision; a missing column raises."""

from __future__ import annotations

import io
from datetime import date
from decimal import Decimal

import polars as pl
import pytest

from fin.ingest import pyield

ROW = {"raw_sha256": "a" * 64, "ingest_run_id": "r"}


def _blob(df: pl.DataFrame) -> bytes:
    buf = io.BytesIO()
    df.write_parquet(buf)
    return buf.getvalue()


def test_bond_rate_rounds_to_anbima_precision() -> None:
    # LTN 2027-04-01 on 2026-10-29: PU 948.687824, indicative 13.7549 % (equal to ANBIMA's own file, pyield_data.md)
    df = pl.DataFrame(
        {
            "data_referencia": [date(2026, 10, 29)], "titulo": ["LTN"], "codigo_selic": [100000],
            "data_base": [date(2025, 1, 10)], "data_vencimento": [date(2027, 4, 1)], "pu": [948.6878240000001],
            "taxa_compra": [0.137599], "taxa_venda": [0.136999], "taxa_indicativa": [0.13754900000000002],
        }
    )  # fmt: skip
    (p,) = list(pyield.parse_payload(_blob(df), {**ROW, "dataset_id": "anbima_tpf"}))
    r = p.frame.row(0, named=True)
    assert p.partition == "year=2026" and r["pu_brl"] == Decimal("948.687824")
    assert r["indicative_rate_pct"] == Decimal("13.754900")
    assert pyield.BOND_RATE.split(p.frame)[1].height == 0


def test_missing_column_raises() -> None:
    df = pl.DataFrame({"reference_date": [date(2026, 1, 2)], "inflation": [0.5]})
    with pytest.raises(pyield.LayoutError):
        list(pyield.parse_payload(_blob(df), {**ROW, "dataset_id": "vna_ntnb"}))
