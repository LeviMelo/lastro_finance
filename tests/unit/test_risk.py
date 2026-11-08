"""Risk statistics of a value path: a known drawdown, zero volatility on a flat path, beta of a scaled index."""

from __future__ import annotations

import math
from datetime import date, timedelta

import polars as pl

from fin.analytics import risk
from fin.analytics.risk import stats


def _path(values: list[float]) -> pl.DataFrame:
    return pl.DataFrame({"trade_date": [date(2025, 1, 1) + timedelta(days=i) for i in range(len(values))],
                         "value_brl": values})  # fmt: skip


def test_drawdown_peak_and_trough() -> None:
    s = stats(_path([100, 120, 90, 110, 130]))
    assert abs(s["max_drawdown"] - (90 / 120 - 1)) < 1e-12  # type: ignore[operator]
    assert s["peak"] == date(2025, 1, 2) and s["trough"] == date(2025, 1, 3)


def test_flat_path_has_no_volatility_and_beta_of_twice_the_index_is_two() -> None:
    assert stats(_path([100.0] * 5))["volatility"] == 0
    ix = [100.0, 101.0, 99.5, 102.0, 101.0, 103.0]
    port = [100 * math.exp(2 * math.log(v / ix[0])) for v in ix]  # log returns exactly twice the index's
    idx = _path(ix).rename({"value_brl": "level"})
    assert abs(stats(_path(port), idx)["beta"] - 2.0) < 1e-9  # type: ignore[operator]


def test_value_path_follows_the_tesouro_sell_pu() -> None:
    import duckdb

    con = duckdb.connect()
    con.execute("CREATE TABLE tesouro_price_daily (instrument_id VARCHAR, base_date DATE, sell_pu DECIMAL(18,2))")
    con.execute("INSERT INTO tesouro_price_daily VALUES ('t1','2026-01-02',1000),('t1','2026-01-05',1010),"
                "('t1','2026-01-06',0)")  # fmt: skip
    h = pl.DataFrame({"instrument_id": ["t1"], "asset_class": ["tesouro_direto"], "quantity": [2.0]})
    p = risk.value_path(con, h, date(2026, 1, 1), date(2026, 1, 31))
    assert p["value_brl"].to_list() == [2000.0, 2020.0]  # a zero PU (no sale that day) is not a price


def test_an_etf_line_is_looked_through_its_latest_delivered_portfolio() -> None:
    import duckdb

    con = duckdb.connect()
    con.execute("""
        CREATE TABLE etf_link AS SELECT 'E' AS instrument_id, 'F' AS fund_cnpj, true AS verified;
        CREATE TABLE etf_position AS SELECT * FROM (VALUES
            (1, 'F', DATE '2026-01-01', TIMESTAMPTZ '2026-02-10 12:00:00+00', 'AAAA3', 60.0),
            (1, 'F', DATE '2026-01-01', TIMESTAMPTZ '2026-02-10 12:00:00+00', NULL, 40.0),
            (2, 'F', DATE '2026-02-01', TIMESTAMPTZ '2026-03-10 12:00:00+00', 'BBBB3', 100.0))
          t(doc_id, fund_cnpj, reference_month, delivered_at, asset_code, market_value_brl);
        CREATE TABLE instrument_identifier AS SELECT * FROM (VALUES ('a', 'TICKER', 'AAAA3'), ('b', 'TICKER', 'BBBB3'))
          t(instrument_id, scheme, value);
        CREATE TABLE issuer_instrument AS SELECT * FROM (VALUES ('a', 'ia'), ('b', 'ib')) t(instrument_id, issuer_id);
        CREATE TABLE issuer AS SELECT * FROM (VALUES ('ia', 'Bancos'), ('ib', 'Energia')) t(issuer_id, sector);
    """)  # fmt: skip
    h = pl.DataFrame({"instrument_id": ["E"], "weight": [0.5]})
    feb = dict(risk.sector_exposure(con, h, date(2026, 2, 20)).rows())  # the March delivery is not known yet
    assert feb == {"Bancos": 0.3, "ETF: outros ativos": 0.2}
    mar = dict(risk.sector_exposure(con, h, date(2026, 3, 20)).rows())
    assert mar == {"Energia": 0.5}
