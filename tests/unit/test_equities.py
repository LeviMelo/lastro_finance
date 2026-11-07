"""Identity and price_daily rules: one row per session (yearly file preferred), internal codes linked to ISINs only
one-to-one, prices per unit exact, and the currency of each era resolved by date."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from fractions import Fraction

import polars as pl

from fin.core import equities


def _q(rows: list[tuple[date, str, str, str, str]]) -> pl.DataFrame:
    return pl.DataFrame(
        rows, schema=["trade_date", "ticker", "isin", "close", "raw_locator"], orient="row"
    ).with_columns(pl.lit(10, dtype=pl.Int16).alias("tpmerc"), pl.lit("a" * 64).alias("raw_sha256"))


def test_dedupe_prefers_the_yearly_file_and_counts_conflicts() -> None:
    d = date(2026, 10, 30)
    q = _q(
        [
            (d, "PETR4", "BRPETRACNPR6", "45.00", "member=COTAHIST_D30102026.TXT;line=9"),
            (d, "PETR4", "BRPETRACNPR6", "45.01", "member=COTAHIST_A2026.TXT;line=7"),
            (d, "VALE3", "BRVALEACNOR0", "60.00", "member=COTAHIST_D30102026.TXT;line=3"),
        ]
    )
    out, conflicts = equities.dedupe(q)
    assert conflicts == 1 and out.height == 2
    assert out.filter(pl.col("ticker") == "PETR4")["close"][0] == "45.01"


def test_codes_link_to_isin_only_one_to_one() -> None:
    rows = [
        (date(1995, 5, 12), "PET 4", "PETRACPN", "1", "x"),
        (date(1995, 5, 15), "PET 4", "BRPETRACNPR6", "1", "x"),
        (date(1995, 5, 12), "AAA 3", "SHAREDCODE", "1", "x"),  # one code, two ISINs: not linked
        (date(1995, 5, 15), "AAA 3", "BRAAAAACNOR1", "1", "x"),
        (date(1995, 5, 12), "BBB 3", "SHAREDCODE", "1", "x"),
        (date(1995, 5, 15), "BBB 3", "BRBBBBACNOR2", "1", "x"),
    ]
    assert equities.link_codes(_q(rows)) == {"PETRACPN": "BRPETRACNPR6"}


def test_currency_of_each_era_and_its_brl_fraction() -> None:
    days = [date(1986, 1, 3), date(1988, 1, 4), date(1989, 6, 1), date(1991, 1, 2), date(1994, 1, 3), date(1994, 7, 4)]
    out = pl.DataFrame({"trade_date": days}).select(*equities._currency())  # pyright: ignore[reportPrivateUsage]
    assert out["currency"].to_list() == ["BRB", "BRC", "BRN", "BRE", "BRR", "BRL"]
    frac = [Fraction(n, d) for n, d in zip(out["brl_num"], out["brl_den"], strict=True)]
    assert frac[4] == Fraction(1, 2750) and frac[3] == frac[4] / 1000 and frac[1] == frac[2] / 1000
    assert frac[0] == frac[1] / 1000 and frac[5] == 1


def test_instrument_id_is_stable() -> None:
    assert equities.instrument_id("BRPETRACNPR6") == equities.instrument_id("BRPETRACNPR6")
    assert equities.instrument_id("BRPETRACNPR6").startswith("I") and len(equities.instrument_id("X")) == 13


def test_unit_price_divides_by_the_quote_factor_exactly() -> None:
    df = pl.DataFrame(
        {"close": [Decimal("12.34")], "fatcot": [1000]}, schema={"close": pl.Decimal(18, 2), "fatcot": pl.Int32}
    )
    price = (pl.col("close").cast(equities.UNIT_PRICE) / pl.col("fatcot").cast(equities.UNIT_PRICE)).cast(
        equities.UNIT_PRICE
    )
    assert df.select(price)["close"][0] == Decimal("0.01234")
