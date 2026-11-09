"""Stock-event ratios from B3's EG marker and from the filing's own text (ADR-0035)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
import pytest

from fin.core import events as ev
from fin.ingest import cvm_ipe_docs as docs

FIX = Path(__file__).parents[1] / "fixtures" / "cvm_ipe_docs"


@pytest.mark.parametrize(
    ("name", "fmt", "ratio"),
    [("telebras_266245.doc", "doc", (1, 10000)), ("bttl_492206.pdf", "pdf", (1, 25))],
)
def test_ratio_read_from_the_filing(name: str, fmt: str, ratio: tuple[int, int]) -> None:
    text, got = docs.doc_text((FIX / name).read_bytes())
    assert got == fmt
    found = {(r["new_shares"], r["old_shares"]) for r in docs.ratios(text)}
    assert ratio in found


@pytest.mark.parametrize(
    ("sentence", "ratio"),
    [
        ("cada 1 (uma) ação existente será desdobrada em 4 (quatro) ações", (4, 1)),
        ("bonificação de 10% (dez por cento) em ações", (11, 10)),
        ("serão atribuídas 1 (uma) nova ação para cada 5 (cinco) ações possuídas", (6, 5)),
        ("o grupamento de 30 (trinta) ações em 1 (uma)", (1, 30)),
        ("na proporção de 1 (uma) ação para 3 (três) ações", (3, 1)),
    ],
)
def test_ratio_phrasings(sentence: str, ratio: tuple[int, int]) -> None:
    assert ratio in {(r["new_shares"], r["old_shares"]) for r in docs.ratios(sentence)}


def test_sniff_stores_by_the_bytes() -> None:
    blob = (FIX / "bttl_492206.pdf").read_bytes()
    kept, ext, record = docs.sniff(blob)
    assert kept == blob and ext == "pdf" and record["format"] == "pdf"


def _event(ratio: tuple[int, int], pc: float, sources: str = "b3_cotahist,cvm_ipe") -> pl.DataFrame:
    return pl.DataFrame({
        "event_id": ["I|REVERSE_SPLIT|2015-11-25|0"], "instrument_id": ["I"], "event_type": ["REVERSE_SPLIT"],
        "ex_date": [date(2015, 11, 25)], "ratio_num": [ratio[0]], "ratio_den": [ratio[1]], "status": ["confirmed"],
        "sources": [sources], "price_check": [pc], "ipe_link": ["L"],
    })  # fmt: skip


def _zones_with(tmp_path: Path, rows: list[tuple[int, int]]) -> object:
    from fin.config import Zones

    z = Zones(tmp_path)
    d = z.staging / "cvm_ipe_docs" / "ipe_ratio" / "all"
    d.mkdir(parents=True)
    pl.DataFrame({"ipe_link": ["L"] * len(rows), "new_shares": [n for n, _ in rows],
                  "old_shares": [o for _, o in rows]}).write_parquet(d / "part.parquet")  # fmt: skip
    return z


def test_filing_ratio_replaces_the_price_ratio(tmp_path: Path) -> None:
    z = _zones_with(tmp_path, [(1, 25), (2, 1)])  # BTTL3 2015: price 24.1x read as 1:24, filing 25:1
    out = ev.filing_ratios(z, _event((1, 24), 24 / 24.14))  # type: ignore[arg-type]  # the move: 1 new per 24.14 old
    assert out["status"].to_list() == ["conflicting", "confirmed"]
    fixed = out.row(1, named=True)
    assert (fixed["ratio_num"], fixed["ratio_den"]) == (1, 25) and fixed["sources"].endswith("cvm_ipe_doc")


def test_filing_ratio_equal_confirms(tmp_path: Path) -> None:
    z = _zones_with(tmp_path, [(1, 25)])
    out = ev.filing_ratios(z, _event((1, 25), 1.03))  # type: ignore[arg-type]
    assert out["status"].to_list() == ["confirmed"] and out["sources"][0].endswith("cvm_ipe_doc")


def test_filing_ratio_that_misses_the_move_is_ignored(tmp_path: Path) -> None:
    z = _zones_with(tmp_path, [(1, 100)])  # stated 1:100, but the price moved 25x
    out = ev.filing_ratios(z, _event((1, 25), 1.0))  # type: ignore[arg-type]
    assert out["status"].to_list() == ["confirmed"] and out["sources"][0] == "b3_cotahist,cvm_ipe"
