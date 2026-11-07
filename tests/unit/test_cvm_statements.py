"""CVM DFP members parse to exact account values with their scale; the index gives every version's delivery date;
an unknown member or column is refused."""

from __future__ import annotations

import io
import zipfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import polars as pl
import pytest

from fin.ingest import cvm_statements as cvm

FIX = Path(__file__).parents[1] / "fixtures" / "cvm_dfp_itr"
ROW = {"raw_sha256": "a" * 64, "ingest_run_id": "run-1"}
MEMBERS = ("dfp_cia_aberta_2024.csv", "dfp_cia_aberta_BPA_con_2024.csv", "dfp_cia_aberta_DRE_con_2024.csv")


def _zip(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in members.items():
            z.writestr(name, data)
    return buf.getvalue()


def _parsed() -> dict[str, pl.DataFrame]:
    """The fixture's byte-exact member lines, zipped the way CVM ships them."""
    blob = _zip({n: (FIX / n).read_bytes() for n in MEMBERS})
    out: dict[str, pl.DataFrame] = {}
    for p in cvm.parse_zip(blob, ROW):
        good, bad = cvm.CONTRACTS[p.dataset_id].split(p.frame)
        assert bad.height == 0
        out[p.partition] = good
    return out


def test_balance_sheet_value_and_scale() -> None:
    bpa = _parsed()["form=dfp/year=2024/statement=BPA_con"]
    itau = bpa.filter(
        pl.col("cnpj") == "60.872.504/0001-23", pl.col("account_code") == "1", pl.col("period_order") == "ÚLTIMO"
    ).row(0, named=True)
    assert itau["value"] == Decimal("2854475000.0") and itau["scale"] == "MIL" and itau["period_start"] is None
    assert itau["raw_locator"].startswith("member=dfp_cia_aberta_BPA_con_2024.csv;line=")


def test_income_statement_has_period_start() -> None:
    dre = _parsed()["form=dfp/year=2024/statement=DRE_con"]
    assert set(dre["period_start"].drop_nulls()) >= {date(2024, 1, 1)}
    assert set(dre["statement"]) == {"DRE"} and set(dre["consolidation"]) == {"con"}


def test_index_gives_delivery_date_and_version() -> None:
    doc = _parsed()["form=dfp/year=2024"]
    assert doc.height == 2 and doc["received_on"].is_not_null().all() and doc["version"].min() >= 1


def test_unknown_member_or_column_is_refused() -> None:
    with pytest.raises(cvm.LayoutError):
        list(cvm.parse_zip(_zip({"dfp_cia_aberta_XYZ_con_2024.csv": b"a;b\r\n"}), ROW))
    head = (FIX / MEMBERS[1]).read_bytes().replace(b"VL_CONTA", b"VL_NOVO", 1)
    with pytest.raises(cvm.LayoutError):
        list(cvm.parse_zip(_zip({MEMBERS[1]: head}), ROW))
