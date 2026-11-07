"""The query layer: `catalog.duckdb`, a DuckDB file of views over the Parquet zones (PLAN §4.2; ADR-0017).

Nothing is copied into DuckDB: every object is a view over the Parquet files, so the catalog is small, rebuilt in
seconds (`fin catalog`) and never out of date with the files. Views that only reshape staging (`fundamental_fact`)
stay views instead of core copies: storage stays lean (ADR-0014).

Views:
- core: `instrument`, `instrument_identifier`, `price_daily`, `series_observation`, `series_definition`,
  `corporate_event`; derived: `adjustment_factor`;
- `fundamental_fact`: CVM statement lines with the scale applied (`value_brl`), the delivery date of the version
  (`received_on`, knowledge date) and `issuer_cnpj` as 14 digits;
- `price_adjusted`: standard-lot closes with split and cash adjustment to today's basis (derived on read);
- `fii_distribution`: FII/Fiagro distributions with their delivery minute;
- `intraday_bar`: Yahoo 5-minute bars (tier U);
- macro `universe(date, asset_class)`: instruments trading in the 30 days up to a date, delisted later or not.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from fin.config import Zones


def _glob(path: Path) -> str:
    return str(path).replace("\\", "/")


def _rp(path: Path) -> str:
    """A Parquet scan with hive detection off: partition folders (`statement=BPA_con`) must not shadow columns."""
    return f"read_parquet('{_glob(path)}', hive_partitioning = false)"


def _scan(path: Path) -> str:
    return f"SELECT * FROM {_rp(path)}"


def views(z: Zones) -> dict[str, str]:
    c, d, s = z.core, z.derived, z.staging
    out = {
        "instrument": _scan(c / "instrument" / "*.parquet"),
        "instrument_identifier": _scan(c / "instrument_identifier" / "*.parquet"),
        "price_daily": _scan(c / "price_daily" / "*.parquet"),
        "series_observation": _scan(c / "series_observation" / "*.parquet"),
        "series_definition": _scan(c / "series_definition" / "*.parquet"),
        "corporate_event": _scan(c / "corporate_event" / "*.parquet"),
        "issuer": _scan(c / "issuer" / "*.parquet"),
        "issuer_instrument": _scan(c / "issuer_instrument" / "*.parquet"),
        "tesouro_bond": _scan(c / "tesouro_bond" / "*.parquet"),
        "tesouro_price_daily": _scan(c / "tesouro_price_daily" / "*.parquet"),
        "adjustment_factor": _scan(d / "adjustment_factor" / "*.parquet"),
        "fundamental_fact": f"""
            WITH lines AS (
                SELECT * FROM {_rp(s / "cvm_dfp_itr" / "statement_line" / "**" / "*.parquet")}
            ), docs AS (
                SELECT form, cnpj, reference_date, version, min(received_on) AS received_on
                FROM {_rp(s / "cvm_dfp_itr" / "document" / "**" / "*.parquet")}
                GROUP BY ALL
            )
            SELECT
                regexp_replace(l.cnpj, '[^0-9]', '', 'g') AS issuer_cnpj, l.cd_cvm, l.company_name, l.form,
                l.reference_date, l.version, d.received_on, l.statement, l.consolidation, l.period_order,
                l.period_start, l.period_end, l.equity_column, l.account_code, l.account_name, l.fixed_account,
                l.value AS value_as_filed, l.scale,
                CAST(l.value * CASE l.scale WHEN 'MIL' THEN 1000 ELSE 1 END AS DECIMAL(38, 10)) AS value_brl,
                l.raw_sha256, l.raw_locator
            FROM lines l LEFT JOIN docs d USING (form, cnpj, reference_date, version)
        """,
        "price_adjusted": """
            WITH p AS (
                SELECT instrument_id, trade_date, CAST(close AS DOUBLE) AS close
                FROM price_daily WHERE market_segment = 'lote_padrao'
            ), f AS (
                SELECT instrument_id, ex_date, split_factor, split_factor * cash_factor AS total_factor
                FROM adjustment_factor
            )
            SELECT p.instrument_id, p.trade_date, p.close,
                   p.close * coalesce(exp(sum(ln(f.split_factor))), 1) AS close_split_adjusted,
                   p.close * coalesce(exp(sum(ln(f.total_factor))), 1) AS close_adjusted
            FROM p LEFT JOIN f ON f.instrument_id = p.instrument_id AND f.ex_date > p.trade_date
            GROUP BY p.instrument_id, p.trade_date, p.close
        """,
        "focus_expectation": _scan(s / "bcb_focus" / "expectation" / "**" / "*.parquet"),
        "copom_decision": _scan(s / "bcb_copom" / "decision" / "**" / "*.parquet"),
        "ima_component": _scan(s / "anbima_ima" / "ima_component" / "**" / "*.parquet"),
        "fii_distribution": f"""
            SELECT d.*, l.delivered_at
            FROM {_rp(s / "b3_fundosnet" / "distribution" / "**" / "*.parquet")} d
            LEFT JOIN (
                SELECT doc_id, min(delivered_at) AS delivered_at
                FROM {_rp(s / "b3_fundosnet" / "listing" / "**" / "*.parquet")} GROUP BY doc_id
            ) l USING (doc_id)
        """,
        "intraday_bar": f"""
            SELECT DISTINCT ON (symbol, bar_start) *
            FROM {_rp(s / "yahoo_intraday" / "bar" / "**" / "*.parquet")}
        """,
    }
    return out


def build(z: Zones) -> list[str]:
    """(Re)create every view whose files exist. Returns the names created."""
    made: list[str] = []
    tmp = z.catalog.with_suffix(".duckdb.tmp")
    tmp.unlink(missing_ok=True)
    con = duckdb.connect(str(tmp))
    try:
        for name, sql in views(z).items():
            try:
                con.execute(f"CREATE OR REPLACE VIEW {name} AS {sql}")
                con.execute(f"SELECT * FROM {name} LIMIT 0")
                made.append(name)
            except duckdb.Error:
                con.execute(f"DROP VIEW IF EXISTS {name}")  # its files do not exist yet
        if {"instrument", "price_daily"} <= set(made):
            # point-in-time universe (PLAN §4.4): instruments with a standard-lot session in the 30 days up to `d`,
            # whatever happened to them later (delisted ones included: no survivorship bias)
            con.execute(
                """
                CREATE OR REPLACE MACRO universe(d, cls) AS TABLE
                SELECT i.instrument_id, i.asset_class, max(p.trade_date) AS last_session_on_or_before
                FROM instrument i JOIN price_daily p USING (instrument_id)
                WHERE p.market_segment = 'lote_padrao' AND p.trade_date BETWEEN CAST(d AS DATE) - INTERVAL 30 DAY
                      AND CAST(d AS DATE) AND (cls IS NULL OR i.asset_class = cls)
                GROUP BY ALL
                """
            )
            made.append("universe()")
    finally:
        con.close()
    tmp.replace(z.catalog)
    return made
