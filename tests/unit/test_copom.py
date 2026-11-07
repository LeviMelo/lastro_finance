"""Copom history: one row per decision, intra-meeting bias changes kept, the current decision open-ended."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import polars as pl

from fin.ingest import copom

FIX = Path(__file__).parents[1] / "fixtures" / "bcb_copom" / "historicotaxasjuros.json"


def test_decisions() -> None:
    df = copom.parse_decisions(FIX.read_bytes(), {"raw_sha256": "a" * 64, "ingest_run_id": "r"})
    good, bad = copom.DECISION.split(df)
    assert (good.height, bad.height) == (290, 0)
    assert good.filter(pl.col("meeting") == 33).height == 3  # 1999: two changes by the president's use of the bias
    last = good.sort("effective_from").row(-1, named=True)
    assert last["meeting"] == 282 and last["effective_to"] is None and last["target"] == Decimal("13.75")
    assert good.filter(pl.col("meeting") == 1)["effective_from"][0] == date(1996, 7, 1)
