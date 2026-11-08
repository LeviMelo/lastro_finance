"""ETF NAV and link: the latest delivered version wins; a name match is verified only by price against NAV."""

from __future__ import annotations

import duckdb

from fin.catalog import ETF_SQL


def _con() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("""
        CREATE TABLE etf_daily AS SELECT * FROM (VALUES
            (1, 'A', 'fundosnet', DATE '2026-01-02', 100.0, TIMESTAMP '2026-01-05 12:00', 'ISHARES BOVA'),
            (2, 'A', 'fundosnet', DATE '2026-01-02', 101.0, TIMESTAMP '2026-01-06 12:00', 'ISHARES BOVA'),  -- again
            (3, 'A', 'fundosnet', DATE '2026-01-05', 102.0, TIMESTAMP '2026-01-06 13:00', 'ISHARES BOVA'),
            (4, 'B', 'fundosnet', DATE '2026-01-02', 10.0, TIMESTAMP '2026-01-05 12:00', 'IT NOW IDIV'))
          t(doc_id, fund_cnpj, source, reference_date, quota_value_brl, delivered_at, trading_name);
        CREATE TABLE instrument AS SELECT * FROM (VALUES
            ('i1', 'BRBOVACTF003', 'ISHARES BOVA', '14'), ('i2', 'BRDIVOCTF003', 'IT NOW IDIV', '14'))
          t(instrument_id, primary_value, short_name, codbdi);
        CREATE TABLE price_daily AS SELECT * FROM (VALUES
            ('i1', DATE '2026-01-02', 'lote_padrao', 101.2), ('i1', DATE '2026-01-05', 'lote_padrao', 101.9),
            ('i2', DATE '2026-01-02', 'lote_padrao', 12.0))
          t(instrument_id, trade_date, market_segment, close);
    """)  # fmt: skip
    con.execute(ETF_SQL)
    return con


def test_latest_delivered_version_is_the_nav() -> None:
    con = _con()
    assert con.execute("SELECT quota_value_brl FROM etf_nav WHERE fund_cnpj = 'A' AND reference_date = '2026-01-02'"
                       ).fetchall() == [(101.0,)]  # fmt: skip


def test_link_is_verified_by_price_not_by_name() -> None:
    con = _con()
    rows = dict(con.execute("SELECT fund_cnpj, verified FROM etf_link").fetchall())
    assert rows == {"A": True, "B": False}  # B trades at 1.2x its NAV: a candidate, reported by quality
