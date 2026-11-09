"""B3 daily bulletin PDF (ADR-0034): page selection, index compositions and lending, on page subsets of three real
bulletins (tests/fixtures/b3_bdi_pdf/README.md), one per layout: 2022 (two portfolios on a quadrimester's first
session; lending as 'Banco de Títulos'), 2024 and 2026."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
import zstandard

from fin.ingest import b3_bdi_pdf as m

FIX = Path(__file__).parents[1] / "fixtures" / "b3_bdi_pdf"
DAYS = {"20220901": date(2022, 9, 1), "20240902": date(2024, 9, 2), "20261105": date(2026, 11, 5)}


def _load(day: str) -> tuple[list[str], list[int]]:
    texts = m.page_texts((FIX / f"BDI_00_{day}.subset.pdf.zst").read_bytes())
    return texts, list(range(1, len(texts) + 1))


@pytest.mark.parametrize("day", DAYS)
def test_extract_keeps_every_page_of_a_subset(day: str) -> None:
    pdf = zstandard.ZstdDecompressor().decompress((FIX / f"BDI_00_{day}.subset.pdf.zst").read_bytes())
    kept, ext, record = m.extract_pages_local(pdf)
    assert ext == "pzst" and kept[:4] == m.ZSTD_MAGIC
    assert record["kept_pages"] == list(range(1, record["pages"] + 1))
    assert len(m.page_texts(kept)) == record["pages"]


def test_not_a_pdf_is_absent() -> None:
    with pytest.raises(m.NotData):
        m.extract_pages(b"<html>erro</html>")  # refused before any pool process starts


@pytest.mark.parametrize(
    ("day", "qty", "weight", "weights_on", "period"),
    [
        ("20220901", "4380195841", "3.1572", date(2022, 9, 1), (date(2022, 5, 1), date(2022, 8, 31))),
        ("20240902", "4394835131", "2.5172", date(2024, 8, 30), (date(2024, 9, 1), date(2024, 12, 31))),
        ("20261105", "4043349180", "2.4498", date(2026, 9, 4), (date(2026, 9, 1), date(2026, 12, 31))),
    ],
)
def test_ibovespa_first_row(day: str, qty: str, weight: str, weights_on: date, period: tuple[date, date]) -> None:
    rows, _ = m.parse_compositions(*_load(day), DAYS[day])
    r = rows[0]
    assert (r["index_name"], r["ticker"]) == ("IBOVESPA", "ABEV3")
    assert r["theoretical_qty"] == Decimal(qty) and r["weight_pct"] == Decimal(weight)
    assert r["weights_on"] == weights_on and (r["period_start"], r["period_end"]) == period


def test_whole_index_adds_up_to_the_printed_total() -> None:
    _, totals = m.parse_compositions(*_load("20240902"), DAYS["20240902"])
    ibov = next(t for t in totals if t["index_name"] == "IBOVESPA")
    assert ibov["n_assets"] == 86 and ibov["qty_sum_ok"] is True


def test_quadrimester_start_prints_two_portfolios() -> None:
    rows, totals = m.parse_compositions(*_load("20220901"), DAYS["20220901"])
    periods = {(t["index_name"], t["period_start"]) for t in totals}
    assert {("IBOVESPA", date(2022, 5, 1)), ("IBOVESPA", date(2022, 9, 1))} <= periods
    both = [t for t in totals if t["index_name"] == "IBOVESPA"]
    assert all(t["qty_sum_ok"] for t in both)
    assert {r["period_start"] for r in rows if r["index_name"] == "IBOVESPA"} == {date(2022, 5, 1), date(2022, 9, 1)}


def test_2026_tables_print_no_total() -> None:
    _, totals = m.parse_compositions(*_load("20261105"), DAYS["20261105"])
    assert totals[0]["index_name"] == "IBOVESPA" and totals[0]["n_assets"] == 76
    assert totals[0]["theoretical_qty_total"] is None and totals[0]["qty_sum_ok"] is None


def test_legacy_lending_balance() -> None:
    trades, opens = m.parse_lending(*_load("20220901"), DAYS["20220901"])
    assert not trades and opens
    o = opens[0]
    assert (o["trade_date"], o["ticker"], o["isin"], o["market"]) == (date(2022, 8, 31), "A1BB34", None, "Total")
    assert o["quantity"] == Decimal(207) and o["value_brl"] == Decimal("7503.80")
    assert all(r["quantity"] is not None and r["market"] == "Total" for r in opens)


@pytest.mark.parametrize("day", ["20240902", "20261105"])
def test_lending_rows_all_parse(day: str) -> None:
    trades, opens = m.parse_lending(*_load(day), DAYS[day])
    assert trades and opens
    assert all(r["quantity"] is not None and r["market"] is not None for r in trades + opens)


def test_lending_2024_wrapped_rows() -> None:
    trades, opens = m.parse_lending(*_load("20240902"), DAYS["20240902"])
    amd = next(r for r in trades if r["ticker"] == "A1MD34")
    assert (amd["market"], amd["n_contracts"], amd["quantity"]) == ("Registro", 2, Decimal(1300))
    assert amd["value_brl"] == Decimal("135616.00") and amd["borrower_rate_avg"] == Decimal("13.30")
    aapl = opens[0]
    assert (aapl["ticker"], aapl["isin"], aapl["market"]) == ("AAPL34", "BRAAPLBDR004", "Neg. Eletrônica D+0")
    assert (aapl["quantity"], aapl["avg_price_brl"], aapl["value_brl"]) == (
        Decimal(400), Decimal("58.4100"), Decimal("23364.00"))  # fmt: skip


def test_lending_totals_equal_the_markets() -> None:
    _, opens = m.parse_lending(*_load("20261105"), DAYS["20261105"])
    by: dict[str, list[Decimal]] = {}
    total: dict[str, Decimal] = {}
    for r in opens:
        if r["market"] == "Total":
            total[r["ticker"]] = r["quantity"]
        else:
            by.setdefault(r["ticker"], []).append(r["quantity"])
    complete = [t for t in total if t in by]
    assert complete and all(sum(by[t]) == total[t] for t in complete)


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("4.394.835.131", "4394835131"), ("4,394,835,131", "4394835131"), ("2,5172", "2.5172"), ("2.5172", "2.5172"),
        ("1.234,56", "1234.56"), ("1,234.56", "1234.56"), ("0,123", "0.123"), ("8.00%", "8.00"), ("125", "125"),
    ],
)  # fmt: skip
def test_numbers_in_either_convention(text: str, value: str) -> None:
    assert m._dec(text) == Decimal(value)  # pyright: ignore[reportPrivateUsage]  # pt-BR in most bulletins, en-US in some (2023-07-19, 2025-01, 2026-06-25)


def test_wrapped_row_date_is_rejoined() -> None:
    lines = [
        "06/01/202",
        "5",
        "A1ME34 BRA1MEBDR000 AMETEK INC Registro 0 0 0.00 12.00% 12.00% 12.00% 12.00% 12.00% 12.00%",
    ]
    trades, _ = m.parse_lending(
        ["Data Ticker ISIN Empresa ou Fundo Mercado\n" + "\n".join(lines)], [1], date(2025, 1, 6)
    )
    assert len(trades) == 1 and trades[0]["trade_date"] == date(2025, 1, 6) and trades[0]["market"] == "Registro"
    assert trades[0]["lender_rate_avg"] == Decimal("12.00")
