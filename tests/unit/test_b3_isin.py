"""B3 ISIN database: issuer code -> CNPJ, exact."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from fin.ingest import b3_isin

FIX = Path(__file__).parents[1] / "fixtures" / "b3_isin"


def test_emitter_lines() -> None:
    row = {"raw_sha256": "x", "ingest_run_id": "r", "notes": "full|EMISSOR.TXT"}
    (p,) = list(b3_isin.parse_payload((FIX / "EMISSOR_excerpt.TXT").read_bytes(), row))
    good, bad = b3_isin.EMITTER.split(p.frame)
    assert bad.height == 0 and good.height == 6
    r = good.filter(good["code"] == "COGN").row(0, named=True)
    assert (r["cnpj"], r["since"]) == ("02800026000140", date(2018, 6, 28)) and r["name"].startswith("COGNA EDUCA")


def test_other_members_are_archived_not_parsed() -> None:
    assert list(b3_isin.parse_payload(b"x", {"notes": "daily|NUMERACA_D.TXT"})) == []
