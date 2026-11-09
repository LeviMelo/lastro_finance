"""Index membership: an ETF is matched to the index its holdings agree with; before B3's bulletin, the matched
ETF's holdings stand in (ADR-0036)."""

from __future__ import annotations

from datetime import date

import polars as pl

from fin.core import indices

IBOV = ["ABEV3", "B3SA3", "ITUB4", "PETR4", "VALE3", "WEGE3", "BBAS3", "BBDC4", "ITSA4", "RENT3"]
SMLL = ["AZZA3", "CYRE3", "EZTC3", "MRVE3", "TEND3", "VIVA3", "SMTO3", "SLCE3", "POMO4", "RAPT4"]


def _official(months: list[date]) -> pl.DataFrame:
    rows = [(m.replace(day=25), name, t) for m in months for name, ts in (("IBOVESPA", IBOV), ("SMLL", SMLL))
            for t in ts]  # fmt: skip
    b, n, t = zip(*rows, strict=True)
    k = len(b)
    return pl.DataFrame({"bulletin_date": list(b), "index_name": list(n), "ticker": list(t),
                         "theoretical_qty": [1] * k, "weight_pct": [1.0] * k, "period_start": [None] * k,
                         "period_end": [None] * k, "raw_sha256": ["s"] * k},
                        schema_overrides={"period_start": pl.Date, "period_end": pl.Date})  # fmt: skip


def _holdings(fund: str, tickers: list[str], months: list[date]) -> pl.DataFrame:
    rows = [(fund, m, t) for m in months for t in tickers]
    f, m, t = zip(*rows, strict=True)
    return pl.DataFrame({"fund_cnpj": list(f), "reference_month": list(m), "ticker": list(t),
                         "raw_sha256": ["h"] * len(f)})  # fmt: skip


BDI = [date(2022, 3, 1), date(2022, 4, 1), date(2022, 5, 1)]
EARLY = [date(2019, 1, 1), date(2019, 2, 1)]


def test_etf_matched_to_the_index_it_holds() -> None:
    h = pl.concat([
        _holdings("BOVA", IBOV, EARLY + BDI),
        _holdings("SMAL", SMLL[:-1], BDI),  # one name short: Jaccard 0.9
        _holdings("MIXD", IBOV[:5] + SMLL[:5], BDI),  # tracks neither
    ])  # fmt: skip
    m = indices.etf_index(_official(BDI), h)
    assert dict(zip(m["fund_cnpj"], m["index_name"], strict=True)) == {"BOVA": "IBOVESPA", "SMAL": "SMLL"}


def test_membership_uses_b3_then_the_etf_before() -> None:
    off = _official(BDI)
    h = _holdings("BOVA", IBOV, EARLY + BDI)
    mem = indices.membership(off, h, indices.etf_index(off, h))
    ibov = mem.filter(pl.col("index_name") == "IBOVESPA")
    assert set(ibov.filter(pl.col("source") == "etf_cda")["month"].to_list()) == set(EARLY)
    assert set(ibov.filter(pl.col("source") == "b3_bdi")["month"].to_list()) == set(BDI)
    assert ibov.filter(pl.col("month") == EARLY[0])["ticker"].sort().to_list() == sorted(IBOV)


def test_a_month_without_bulletin_takes_the_quadrimester_portfolio() -> None:
    off = _official([date(2023, 3, 1)]).with_columns(
        pl.lit(date(2023, 1, 1)).alias("period_start"), pl.lit(date(2023, 4, 30)).alias("period_end")
    )
    may = _official([date(2023, 5, 1)]).with_columns(
        pl.lit(date(2023, 5, 1)).alias("period_start"), pl.lit(date(2023, 8, 31)).alias("period_end")
    )
    h = _holdings("BOVA", IBOV, [date(2023, 3, 1)])
    mem = indices.membership(pl.concat([off, may]), h, indices.etf_index(off, h))
    apr = mem.filter((pl.col("index_name") == "IBOVESPA") & (pl.col("month") == date(2023, 4, 1)))
    assert apr.height == len(IBOV) and apr["as_of"].unique().to_list() == [date(2023, 3, 25)]
