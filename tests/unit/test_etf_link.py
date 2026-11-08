"""ETF NAV and link in core: the latest delivered version wins, CVM fills the years before Fundos.NET, and a link
values nothing until the price confirms it (ADR-0029)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import polars as pl

from fin.config import Zones
from fin.core import etfs
from fin.store.tables import write_parquet

UTC = UTC
PROV = {"raw_sha256": "x", "raw_locator": "l", "ingest_run_id": "r"}


def _home(tmp_path: Path) -> Zones:
    z = Zones(tmp_path)
    s = z.staging
    q = pl.Decimal(38, 12)
    daily = pl.DataFrame(
        {
            "doc_id": [1, 2, 3, 4],
            "fund_cnpj": ["10406511000161", "10406511000161", "10406511000161", "31024153000100"],
            "reference_date": [date(2026, 1, 2), date(2026, 1, 2), date(2026, 1, 5), date(2026, 1, 2)],
            "quota_value_brl": pl.Series([Decimal(100), Decimal(101), Decimal(102), Decimal(10)], dtype=q),
        }
    ).with_columns(**{k: pl.lit(v) for k, v in PROV.items()})
    write_parquet(daily, s / "b3_fundosnet_daily" / "daily" / "a.parquet")
    listing = pl.DataFrame(
        {
            "doc_id": [1, 2, 3, 4],
            "delivered_at": [datetime(2026, 1, 5, 15, tzinfo=UTC), datetime(2026, 1, 6, 15, tzinfo=UTC),
                             datetime(2026, 1, 6, 16, tzinfo=UTC), datetime(2026, 1, 5, 15, tzinfo=UTC)],
            "version": [1, 2, 1, 1],
            "trading_name": ["ISHARES BOVA", "ISHARES BOVA", "ISHARES BOVA", "IT NOW IDIV"],
        }
    )  # fmt: skip
    write_parquet(listing, s / "b3_fundosnet_daily" / "listing" / "a.parquet")
    cvm = pl.DataFrame(
        {
            "cnpj": ["10.406.511/0001-61", "99.999.999/0001-99"],
            "reference_date": [date(2017, 1, 2), date(2017, 1, 2)],
            "quota_value_brl": pl.Series([Decimal(60), Decimal(5)], dtype=q),
        }
    ).with_columns(
        *[pl.lit(None, dtype=pl.Decimal(38, 2)).alias(c) for c in ("net_assets_brl", "portfolio_value_brl",
                                                                   "subscriptions_brl", "redemptions_brl")],
        pl.lit(None, dtype=pl.Int64).alias("holders"),
        **{k: pl.lit(v) for k, v in PROV.items()},
    )  # fmt: skip
    write_parquet(cvm, s / "cvm_fi_inf_diario" / "daily" / "a.parquet")
    write_parquet(
        pl.DataFrame(
            {"instrument_id": ["i1", "i2"], "short_name": ["ISHARES BOVA", "IT NOW IDIV"], "codbdi": ["14", "14"]}
        ),
        z.core / "instrument" / "instrument.parquet",
    )  # fmt: skip
    write_parquet(
        pl.DataFrame(
            {
                "instrument_id": ["i1", "i2", "i1", "i2"],
                "scheme": ["ISIN", "ISIN", "TICKER", "TICKER"],
                "value": ["BRBOVACTF003", "BRDIVOCTF003", "BOVA11", "DIVO11"],
            }
        ),
        z.core / "instrument_identifier" / "instrument_identifier.parquet",
    )  # fmt: skip
    write_parquet(
        pl.DataFrame({
            "instrument_id": ["i1", "i1", "i2"], "trade_date": [date(2026, 1, 2), date(2026, 1, 5), date(2026, 1, 2)],
            "market_segment": ["lote_padrao"] * 3, "close": [101.2, 101.9, 12.0],
        }),
        z.core / "price_daily" / "p.parquet",
    )  # fmt: skip
    return z


def test_latest_delivered_version_wins_and_cvm_fills_before(tmp_path: Path) -> None:
    nav = etfs.nav_frame(_home(tmp_path))
    assert nav is not None
    latest = nav.filter(pl.col("is_latest") & (pl.col("fund_cnpj") == "10406511000161")).sort("reference_date")
    assert latest["quota_value_brl"].cast(pl.Float64).to_list() == [60.0, 101.0, 102.0]  # CVM 2017, v2, then 01-05
    assert latest["source"].to_list() == ["cvm_inf_diario", "fundosnet", "fundosnet"]
    assert "99999999000199" not in nav["fund_cnpj"].to_list()  # a CVM fund that is not an ETF stays out


def test_link_is_verified_by_price_not_by_name(tmp_path: Path) -> None:
    z = _home(tmp_path)
    out = etfs.build(z)
    assert out["etf_link"] == 2
    link = pl.read_parquet(z.core / "etf_link" / "etf_link.parquet")
    assert dict(link.select("fund_cnpj", "verified").rows()) == {"10406511000161": True, "31024153000100": False}


def test_a_fixed_income_etf_links_by_b3_listing_and_is_priced_by_the_price_report(tmp_path: Path) -> None:
    z = _home(tmp_path)
    s = z.staging
    write_parquet(
        pl.DataFrame({"doc_id": [9], "fund_cnpj": ["31024153000199"], "reference_date": [date(2026, 1, 2)],
                      "quota_value_brl": pl.Series([Decimal("118.5")], dtype=pl.Decimal(38, 12))})
        .with_columns(**{k: pl.lit(v) for k, v in PROV.items()}),
        s / "b3_fundosnet_daily" / "daily" / "b.parquet",
    )  # fmt: skip
    write_parquet(
        pl.DataFrame({"doc_id": [9], "delivered_at": [datetime(2026, 1, 5, tzinfo=UTC)], "version": [1],
                      "trading_name": ["IT NOW IMA-B"]}),
        s / "b3_fundosnet_daily" / "listing" / "b.parquet",
    )  # fmt: skip
    write_parquet(pl.DataFrame({"type_fund": ["ETF-RF"], "fnet_id": [7], "acronym": ["IMAB"]}),
                  s / "b3_funds_listed" / "listed_fund" / "a.parquet")  # fmt: skip
    write_parquet(pl.DataFrame({"fnet_id": [7], "doc_id": [9]}), s / "b3_funds_listed" / "fund_report" / "a.parquet")
    write_parquet(
        pl.DataFrame({"ticker": ["IMAB11"], "trade_date": [date(2026, 1, 2)], "last_price": [118.55]}),
        s / "b3_pesquisapregao" / "price_report" / "a.parquet",
    )
    etfs.build(z)
    link = pl.read_parquet(z.core / "etf_link" / "etf_link.parquet").filter(pl.col("ticker") == "IMAB11")
    r = link.row(0, named=True)
    assert (r["instrument_id"], r["price_source"], r["methods"], r["verified"]) == (
        None,
        "b3_price_report",
        "b3_listing",
        True,
    )
