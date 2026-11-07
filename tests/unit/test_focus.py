"""Focus tables share one staging shape: reference period by table, both key casings, exact statistics."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from fin.ingest import focus

FIX = Path(__file__).parents[1] / "fixtures" / "bcb_focus"


def _parse(entity: str):  # type: ignore[no-untyped-def]
    row = {"raw_sha256": "a" * 64, "ingest_run_id": "r", "dataset_id": entity.lower()}
    df = focus.parse_expectations((FIX / f"{entity}_top3_2026-10-30.json").read_bytes(), row)
    good, bad = focus.EXPECTATION.split(df)
    assert bad.height == 0
    return good


def test_reference_comes_from_each_table() -> None:
    assert _parse("ExpectativasMercadoSelic")["reference"][0].startswith("R")
    assert set(_parse("ExpectativasMercadoInflacao12Meses")["reference"]) == {"12m"}
    annual = _parse("ExpectativasMercadoAnuais")
    assert annual["survey_date"][0] == date(2026, 10, 30) and annual["reference"][0].isdigit()


def test_lower_case_keys_of_the_top5_tables() -> None:
    top5 = _parse("ExpectativasMercadoTop5Selic").row(0, named=True)
    assert top5["indicator"] == "Selic" and top5["calc_type"] == "C" and str(top5["median"]).startswith("13.75")
    assert top5["cv"] is not None
