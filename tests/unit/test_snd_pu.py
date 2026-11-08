"""SND PU Histórico: layout from real files, exact decimals, layout drift refused."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from fin.ingest import snd_pu
from fin.ingest.base import NotData

FIX = Path(__file__).parents[1] / "fixtures" / "snd_pu_historico"


def _row() -> dict[str, Any]:
    return {"raw_sha256": "a" * 64, "ingest_run_id": "r", "dataset_id": "pu", "notes": "ticker=X"}


def _frame(name: str) -> Any:
    (p,) = list(snd_pu.parse_pu((FIX / name).read_bytes(), _row()))
    assert p.dataset_id == "debenture_pu"
    good, bad = snd_pu.DEBENTURE_PU.split(p.frame)
    assert bad.height == 0
    return good


def test_real_files_parse_exactly() -> None:
    df = _frame("SABP12.txt")
    assert df.height == 737
    first = df.sort("ref_date", descending=True).row(0, named=True)
    assert first["ref_date"] == date(2024, 12, 31) or first["ref_date"] > date(2024, 12, 31)
    d = df.filter(df["ref_date"] == date(2024, 12, 31)).row(0, named=True)
    assert d["par_value_brl"] == Decimal("1052.678070")
    assert d["accrued_interest_brl"] == Decimal("82.855032")
    assert d["premium_brl"] is None
    assert d["pu_brl"] == Decimal("1135.533102")
    assert (d["calc_criterion"], d["situation"], d["ticker"]) == ("Padrão - SND", "Reg.", "SABP12")
    z = _frame("ZZDT21.txt")
    assert z.height == 643 and set(z["situation"]) == {"Exc."}
    assert z["accrued_interest_brl"].null_count() > 0  # "-  " is no value


def test_header_only_answer_is_empty() -> None:
    assert _frame("VALE23_empty.txt").height == 0


def test_layout_drift_raises() -> None:
    blob = (FIX / "ZZDT21.txt").read_bytes()
    with pytest.raises(snd_pu.LayoutError, match="columns changed"):
        list(snd_pu.parse_pu(blob.replace("Prêmio".encode("latin-1"), b"Premio"), _row()))
    with pytest.raises(snd_pu.LayoutError, match="fields"):
        list(snd_pu.parse_pu(blob.replace(b"\tExc.\t", b"\tExc.\tX\t", 1), _row()))
    with pytest.raises(snd_pu.LayoutError, match="unexpected text"):
        list(snd_pu.parse_pu(blob + b"\r\nsurprise\r\n", _row()))


def test_not_a_pu_file() -> None:
    with pytest.raises(NotData):
        list(snd_pu.parse_pu(b"<html>error</html>", _row()))


def test_request_is_day_first() -> None:
    spec = snd_pu.SndPuHistorico()._spec("SABP12", date(1980, 1, 1), date(2026, 11, 8))  # pyright: ignore[reportPrivateUsage]
    assert spec.params == {"op_exc": "False", "ativo": "SABP12", "dt_ini": "01/01/1980", "dt_fim": "08/11/2026"}
    assert spec.locator == "ticker=SABP12"
