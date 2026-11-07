"""COTAHIST parser on real excerpts (docs/sources/b3_cotahist.md). Every number asserted here is read from the
fixture line itself, so the test pins positions and implied decimals, not a remembered quote."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import polars as pl
import pytest

from conftest import FIXTURES
from fin.ingest.b3_cotahist import QUOTE, LayoutError, check_trailer, parse_text

DIR = FIXTURES / "b3_cotahist"


def load(name: str):
    return parse_text((DIR / name).read_bytes().decode("latin-1"), name)


def test_2025_first_record_fields() -> None:
    f = load("COTAHIST_A2025_excerpt.TXT")
    assert f.header_date == date(2025, 12, 30)
    r = f.records.row(0, named=True)
    # 012025012012ITIP11      010FII INTER IPCI           R$  0000000006900 0000000006924 0000000006808 ...
    assert r["trade_date"] == date(2025, 1, 20) and r["codbdi"] == "12" and r["ticker"] == "ITIP11"
    assert r["tpmerc"] == 10 and r["modref"] == "R$"
    assert (r["open"], r["high"], r["low"], r["avg"], r["close"]) == (
        Decimal("69.00"),
        Decimal("69.24"),
        Decimal("68.08"),
        Decimal("68.30"),
        Decimal("68.39"),
    )
    assert r["n_trades"] == 59 and r["qty"] == 1125 and r["volume"] == Decimal("76847.51")
    assert r["expiry"] is None and r["fatcot"] == 1 and r["isin"] == "BRITIPCTF002" and r["dismes"] == 136
    assert r["raw_locator"] == "member=COTAHIST_A2025_excerpt.TXT;line=2"


@pytest.mark.parametrize(
    "name", ["COTAHIST_A1986_excerpt.TXT", "COTAHIST_A2025_excerpt.TXT", "COTAHIST_D06112026_excerpt.TXT"]
)
def test_every_fixture_conforms_and_nothing_is_lost(name: str) -> None:
    f = load(name)
    lines = (DIR / name).read_bytes().count(b"\r\n")
    assert f.records.height == lines - 2
    df = f.records.with_columns(pl.lit("x" * 64).alias("raw_sha256"), pl.lit("run").alias("ingest_run_id"))
    valid, rejected = QUOTE.split(df)
    assert valid.height + rejected.height == df.height
    assert rejected.height == 0, rejected.select("ticker", "reject_rules").to_dicts()


def test_quote_factors_and_old_currency_survive() -> None:
    old = load("COTAHIST_A1986_excerpt.TXT").records
    assert set(old["modref"]) >= {"CZ$"} and 1000 in set(old["fatcot"])
    new = load("COTAHIST_A2025_excerpt.TXT").records
    assert set(new["fatcot"]) == {1, 10, 100, 1000, 10000}
    assert 21 in set(new["tpmerc"])  # undocumented in the 2017 PDF, observed in 2025


def test_option_rows_carry_strike_and_expiry() -> None:
    opt = load("COTAHIST_A2025_excerpt.TXT").records.filter(pl.col("tpmerc").is_in([70, 80]))
    assert opt.height > 0
    assert opt["expiry"].null_count() == 0 and (opt["strike"] > 0).all()


def test_excerpt_trailer_is_refused_full_counts_accepted() -> None:
    f = load("COTAHIST_A2025_excerpt.TXT")
    with pytest.raises(LayoutError):
        check_trailer(f)  # the excerpt keeps the original file's trailer
    n = f.records.height
    check_trailer(type(f)(f.member, f.header_date, n, f.records, f.unparsed))
    check_trailer(type(f)(f.member, f.header_date, n + 2, f.records, f.unparsed))


def test_utf8_line_in_latin1_file_is_repaired_and_flagged() -> None:
    f = load("COTAHIST_A2026_utf8_excerpt.TXT")  # real: B3 wrote "Â" as UTF-8, a 246-byte line
    assert f.unparsed.height == 0 and f.records.height == 3
    r = f.records.filter(pl.col("ticker") == "FR0T5L").row(0, named=True)
    assert r["short_name"] == "FROTA OCEÂNI" and r["isin"] == "BRFR0TACNPA9"
    assert r["raw_locator"].endswith(";decoded=utf-8")
    assert not f.records.filter(pl.col("ticker") != "FR0T5L")["raw_locator"].str.contains("decoded").any()


def test_unrepairable_line_is_quarantined_not_fatal() -> None:
    text = (DIR / "COTAHIST_D06112026_excerpt.TXT").read_bytes().decode("latin-1")
    lines = text.split("\r\n")
    f = parse_text(text.replace(lines[1], lines[1] + "X"), "broken")
    assert f.unparsed.height == 1 and f.unparsed["raw_locator"][0] == "member=broken;line=2"
    assert f.records.height == len(lines) - 4  # header, trailer, the bad line and the final empty split
