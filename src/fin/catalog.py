"""The query layer: `catalog.duckdb`, a DuckDB file of views over the Parquet zones (PLAN §4.2; ADR-0017).

Nothing is copied into DuckDB: every object is a view over the Parquet files, so the catalog is small, rebuilt in
seconds (`fin catalog`) and never out of date with the files. Views that only reshape staging (`fundamental_fact`)
stay views instead of core copies: storage stays lean (ADR-0014).

Views:
- core: `instrument`, `instrument_identifier`, `price_daily`, `series_observation`, `series_definition`,
  `corporate_event`; derived: `adjustment_factor`; quality: `dq_finding` (ADR-0022);
- `fundamental_fact`: CVM statement lines (open data plus the superseded versions from RAD, ADR-0027) with the
  scale applied (`value_brl`), the delivery date of the version
  (`received_on`, knowledge date) and `issuer_cnpj` as 14 digits;
- `price_adjusted`: standard-lot closes with split and cash adjustment to today's basis (derived on read);
- `fii_distribution`: FII/Fiagro distributions with their delivery minute;
- `insider_movement`: CVM VLMO insider positions and trades by role group, with delivery date and latest flag;
- `etf_daily` / `etf_nav`: ETF daily reports (every version / the latest per date), `etf_link` to the instrument;
  `etf_position`: ETF monthly portfolios; `crypto_daily`: Binance daily klines (tier S);
- `us_daily_price`: Tiingo daily prices of US benchmarks and Brazilian ADRs (tier S);
- `price_report_close`: B3 Price Report closes per ticker and day (fixed-income ETFs' only price);
- debentures (ADR-0028): `debenture`, `debenture_terms`, `debenture_pu` (SND accrued PU), `debenture_secondary_price`;
- `intraday_bar`: Yahoo 5-minute bars (tier U);
- macro `universe(date, asset_class)`: instruments trading in the 30 days up to a date, delisted later or not;
- macro `valuation(date)`: per issuer, market cap and P/L, P/VP as known on that date (ADR-0021);
- macro `fii_valuation(date)`: per FII quota, price to NAV and trailing dividend yield as known on that date.
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
    rad_dir = s / "cvm_rad_versions" / "statement_line"
    rad = (
        f"UNION ALL BY NAME SELECT * FROM {_rp(rad_dir / '**' / '*.parquet')}"
        if rad_dir.exists() and any(rad_dir.rglob("*.parquet"))
        else ""
    )
    out = {
        "instrument": _scan(c / "instrument" / "*.parquet"),
        "instrument_identifier": _scan(c / "instrument_identifier" / "*.parquet"),
        "price_daily": _scan(c / "price_daily" / "*.parquet"),
        "series_observation": _scan(c / "series_observation" / "*.parquet"),
        "series_definition": _scan(c / "series_definition" / "*.parquet"),
        "corporate_event": _scan(c / "corporate_event" / "*.parquet"),
        "issuer": _scan(c / "issuer" / "*.parquet"),
        "share_count": _scan(c / "share_count" / "*.parquet"),
        "instrument_link": _scan(c / "instrument_link" / "*.parquet"),
        "issuer_instrument": _scan(c / "issuer_instrument" / "*.parquet"),
        "tesouro_bond": _scan(c / "tesouro_bond" / "*.parquet"),
        "tesouro_price_daily": _scan(c / "tesouro_price_daily" / "*.parquet"),
        "adjustment_factor": _scan(d / "adjustment_factor" / "*.parquet"),
        "dq_finding": _scan(z.quality / "dq_finding" / "*.parquet"),
        # superseded versions recovered from RAD (ADR-0027): the same contract, other versions of the same filings
        "fundamental_fact": f"""
            WITH lines AS (
                SELECT * FROM {_rp(s / "cvm_dfp_itr" / "statement_line" / "**" / "*.parquet")}
                {rad}
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
        "fundamental_metric": """
            -- standard metrics by account name among CVM's fixed accounts: names are stable across the industrial
            -- and the bank templates where codes are not (equity is 2.03 for industrials, 2.07 or 2.08 for banks);
            -- the shallowest matching code wins (docs/evaluation/2026-11-07-fundamentals-mapping.md)
            WITH f AS (
                SELECT *,
                    CASE
                        WHEN statement = 'BPA' AND account_code = '1' THEN 'total_assets'
                        WHEN statement = 'BPA' AND account_name = 'Ativo Circulante' THEN 'current_assets'
                        WHEN statement = 'BPA' AND account_name = 'Caixa e Equivalentes de Caixa' THEN 'cash'
                        WHEN statement = 'BPP' AND account_name = 'Passivo Circulante' THEN 'current_liabilities'
                        WHEN statement = 'BPP' AND account_name = 'Passivo Não Circulante' THEN 'noncurrent_liabilities'
                        WHEN statement = 'BPP'
                            AND account_name IN ('Patrimônio Líquido Consolidado', 'Patrimônio Líquido')
                            THEN 'equity'
                        WHEN statement = 'BPP' AND account_name = 'Patrimônio Líquido Atribuído ao Controlador'
                            THEN 'equity_controlling'
                        WHEN statement = 'BPP' AND account_name IN ('Participação dos Acionistas Não Controladores',
                            'Patrimônio Líquido Atribuído aos Não Controladores') THEN 'noncontrolling_interest'
                        WHEN statement = 'DRE' AND account_code = '3.01' THEN 'revenue'
                        WHEN statement = 'DRE' AND account_name ILIKE 'Resultado Bruto%' THEN 'gross_profit'
                        WHEN statement = 'DRE'
                            AND account_name = 'Resultado Antes do Resultado Financeiro e dos Tributos'
                            THEN 'ebit'
                        WHEN statement = 'DRE' AND account_name ILIKE 'Resultado Antes dos Tributos sobre o Lucro'
                            THEN 'pretax_income'
                        WHEN statement = 'DRE' AND account_name IN ('Lucro/Prejuízo Consolidado do Período',
                            'Lucro ou Prejuízo Líquido Consolidado do Período', 'Lucro/Prejuízo do Período',
                            'Lucro ou Prejuízo Líquido do Período') THEN 'net_income'
                        WHEN statement = 'DRE' AND account_name ILIKE 'Atribuído a%Controladora'
                            THEN 'net_income_controlling'
                        WHEN statement LIKE 'DFC%' AND account_name IN ('Caixa Líquido Atividades Operacionais',
                            'Caixa Líquido das Atividades Operacionais',
                            'Caixa Líquido Atividades Seguradora/Resseguradora') THEN 'cash_from_operations'
                        WHEN statement LIKE 'DFC%' AND account_name IN ('Caixa Líquido Atividades de Investimento',
                            'Caixa Líquido das Atividades de Investimento') THEN 'cash_from_investing'
                        WHEN statement LIKE 'DFC%' AND account_name IN ('Caixa Líquido Atividades de Financiamento',
                            'Caixa Líquido das Atividades de Financiamento') THEN 'cash_from_financing'
                    END AS metric
                FROM fundamental_fact
                WHERE fixed_account AND period_order = 'ÚLTIMO'
            )
            SELECT issuer_cnpj, cd_cvm, company_name, form, reference_date, version, received_on, consolidation,
                   metric, period_start, period_end, account_code, account_name, value_brl, raw_sha256, raw_locator
            FROM f WHERE metric IS NOT NULL
            QUALIFY row_number() OVER (
                PARTITION BY issuer_cnpj, form, reference_date, version, consolidation, metric, period_start, period_end
                ORDER BY length(account_code), account_code
            ) = 1
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
        "cftc_position": _scan(s / "cftc_cot" / "position" / "**" / "*.parquet"),
        "ima_component": _scan(s / "anbima_ima" / "ima_component" / "**" / "*.parquet"),
        "fii_distribution": f"""
            SELECT d.*, l.delivered_at
            FROM {_rp(s / "b3_fundosnet" / "distribution" / "**" / "*.parquet")} d
            LEFT JOIN (
                SELECT doc_id, min(delivered_at) AS delivered_at
                FROM {_rp(s / "b3_fundosnet" / "listing" / "**" / "*.parquet")} GROUP BY doc_id
            ) l USING (doc_id)
        """,
        # ETF NAV and links are built in core (`core/etfs.py`, ADR-0029): views over them stay cheap (as views over
        # CVM's 82 M daily rows they spilled 38 GB of DuckDB temp files, 2026-11-08)
        "etf_daily": _scan(c / "etf_nav" / "*.parquet"),
        "etf_nav": f"SELECT * FROM {_rp(c / 'etf_nav' / '*.parquet')} WHERE is_latest",
        "etf_link": _scan(c / "etf_link" / "*.parquet"),
        # B3 Price Report closes (BVBG.086, 2018-; ADR-0031): the last regular price per ticker and day, the only
        # price of instruments COTAHIST omits (fixed-income ETFs); the latest file of the day wins
        "price_report_close": f"""
            SELECT ticker, trade_date, CAST(last_price AS DOUBLE) AS close, CAST(avg_price AS DOUBLE) AS avg_price,
                   regular_trade_count, regular_quantity, volume_brl, file_date
            FROM {_rp(s / "b3_pesquisapregao" / "price_report" / "**" / "*.parquet")}
            WHERE last_price IS NOT NULL
            QUALIFY row_number() OVER (PARTITION BY ticker, trade_date ORDER BY file_date DESC) = 1
        """,
        # US-listed prices with dividends and splits (Tiingo, tier S, owner token): benchmarks and Brazilian ADRs
        "us_daily_price": f"""
            FROM {_rp(s / "tiingo" / "daily" / "**" / "*.parquet")}
            QUALIFY row_number() OVER (PARTITION BY ticker, trade_date ORDER BY raw_sha256 DESC) = 1
        """,
        # crypto daily klines (Binance, tier S): a daily file and the month's file repeat a day; one row per day
        "crypto_daily": f"""
            FROM {_rp(s / "binance" / "kline" / "**" / "*.parquet")}
            QUALIFY row_number() OVER (PARTITION BY symbol, day ORDER BY raw_sha256) = 1
        """,
        # ETF monthly portfolios (Fundos.NET CDA) with the delivery minute of each document
        "etf_position": f"""
            SELECT p.*, l.delivered_at
            FROM {_rp(s / "b3_fundosnet_cda" / "position" / "**" / "*.parquet")} p
            LEFT JOIN (
                SELECT doc_id, min(delivered_at) AS delivered_at
                FROM {_rp(s / "b3_fundosnet_cda" / "listing" / "**" / "*.parquet")} GROUP BY doc_id
            ) l USING (doc_id)
        """,
        # insider positions and trades by role group (CVM VLMO), each version with its delivery date (knowledge date)
        # and whether it is the latest version of that company-month
        "insider_movement": f"""
            SELECT m.*, d.delivered_on, d.presentation,
                   m.version = max(m.version) OVER (PARTITION BY m.company_cnpj, m.reference_month) AS is_latest
            FROM {_rp(s / "cvm_vlmo" / "movement" / "**" / "*.parquet")} m
            LEFT JOIN (
                SELECT company_cnpj, reference_month, version, min(delivered_on) AS delivered_on,
                       any_value(presentation) AS presentation
                FROM {_rp(s / "cvm_vlmo" / "document" / "**" / "*.parquet")} GROUP BY ALL
            ) d USING (company_cnpj, reference_month, version)
        """,
        # debentures (ADR-0028): terms, SND's accrued daily PU (ticker key; one row per ticker and date) and the
        # secondary-market trade summary; `debenture_id` joins them to core `debenture`
        "debenture": _scan(c / "debenture" / "*.parquet"),
        "debenture_terms": _scan(s / "snd_debentures" / "caracteristicas" / "**" / "*.parquet"),
        "debenture_pu": f"""
            SELECT b.debenture_id, p.*
            FROM {_rp(s / "snd_pu_historico" / "debenture_pu" / "**" / "*.parquet")} p
            LEFT JOIN {_rp(c / "debenture" / "*.parquet")} b USING (ticker)
        """,
        "debenture_secondary_price": f"""
            -- overlapping request windows re-send identical rows: one per distinct value, a restatement stays
            SELECT b.debenture_id, p.*
            FROM (
                FROM {_rp(s / "snd_debentures" / "secondary_price" / "**" / "*.parquet")}
                QUALIFY row_number() OVER (
                    PARTITION BY ticker, trade_date, isin, quantity, n_trades, pu_min_brl, pu_avg_brl, pu_max_brl,
                        pct_of_curve_pu ORDER BY raw_sha256) = 1
            ) p
            LEFT JOIN {_rp(c / "debenture" / "*.parquet")} b USING (ticker)
        """,
        "intraday_bar": f"""
            SELECT DISTINCT ON (symbol, bar_start) *
            FROM {_rp(s / "yahoo_intraday" / "bar" / "**" / "*.parquet")}
        """,
    }
    return out


# Point-in-time valuation (ADR-0021). Everything is as known on `d`: the latest share count and statements CVM had
# received by then, the last standard-lot close in the 30 days up to `d`. Market cap = outstanding common (paid in -
# treasury) x the close of the most traded ON line + outstanding preferred x the close of the most traded PN line, in
# BRL of the day, the shares grown by that line's bonuses and splits between the count and `d`; null when a class
# with shares outstanding has no traded line. Earnings are trailing twelve months of
# `net_income_controlling` (consolidated): the annual figure, or the latest year-to-date + the previous annual - the
# year-to-date a year before. Book value is the latest consolidated equity attributable to the controlling
# shareholders (as filed by banks; equity - non-controlling interest otherwise).
VALUATION = """
CREATE OR REPLACE MACRO valuation(d) AS TABLE
WITH sc AS (
    SELECT issuer_cnpj, reference_date AS shares_reference_date, unit,
           common - coalesce(common_treasury, 0) AS common_out,
           preferred - coalesce(preferred_treasury, 0) AS preferred_out
    FROM share_count
    WHERE unit IS NOT NULL AND received_on <= CAST(d AS DATE)
    -- DFP/ITR first (they state treasury), FRE when no DFP/ITR count is known yet (before 2020)
    QUALIFY row_number() OVER (
        PARTITION BY issuer_cnpj ORDER BY form = 'fre', reference_date DESC, version DESC, form) = 1
), lines AS (
    SELECT s.cnpj AS issuer_cnpj, ii.instrument_id,
           CASE WHEN i.especi LIKE 'ON%' THEN 'ON' WHEN i.especi LIKE 'PN%' THEN 'PN' END AS cls
    FROM issuer s
    JOIN issuer_instrument ii USING (issuer_id)
    JOIN instrument i USING (instrument_id)
    WHERE ii.vt_from <= CAST(d AS DATE) AND ii.vt_to >= CAST(d AS DATE) - INTERVAL 30 DAY
), px0 AS (
    SELECT l.issuer_cnpj, l.cls, p.instrument_id, arg_max(p.ticker, p.trade_date) AS ticker,
           CAST(arg_max(p.close, p.trade_date) AS DOUBLE)
             * arg_max(p.brl_num, p.trade_date) / arg_max(p.brl_den, p.trade_date) AS close_brl,
           max(p.trade_date) AS price_date, sum(CAST(p.volume AS DOUBLE)) AS vol
    FROM lines l JOIN price_daily p USING (instrument_id)
    WHERE l.cls IS NOT NULL AND p.market_segment = 'lote_padrao'
      AND p.trade_date BETWEEN CAST(d AS DATE) - INTERVAL 30 DAY AND CAST(d AS DATE)
    GROUP BY l.issuer_cnpj, l.cls, p.instrument_id
), px AS (
    FROM px0 QUALIFY row_number() OVER (PARTITION BY issuer_cnpj, cls ORDER BY vol DESC) = 1
), grow AS (  -- bonuses and splits of each priced line after the share count: shares x 1 / split_factor
    SELECT px.issuer_cnpj, px.cls, exp(-sum(ln(f.split_factor))) AS g
    FROM px JOIN sc USING (issuer_cnpj)
    JOIN adjustment_factor f ON f.instrument_id = px.instrument_id
         AND f.ex_date > sc.shares_reference_date AND f.ex_date <= CAST(d AS DATE)
    GROUP BY ALL
), sc2 AS (
    SELECT sc.* REPLACE (sc.common_out * coalesce(go.g, 1) AS common_out,
                         sc.preferred_out * coalesce(gp.g, 1) AS preferred_out)
    FROM sc LEFT JOIN (FROM grow WHERE cls = 'ON') go USING (issuer_cnpj)
            LEFT JOIN (FROM grow WHERE cls = 'PN') gp USING (issuer_cnpj)
), cap AS (
    SELECT sc.*, o.ticker AS on_ticker, o.close_brl AS on_close, p.ticker AS pn_ticker, p.close_brl AS pn_close,
           least(o.price_date, p.price_date) AS price_date,
           CASE WHEN (sc.common_out > 0 AND o.close_brl IS NULL) OR (sc.preferred_out > 0 AND p.close_brl IS NULL)
                THEN NULL
                ELSE coalesce(sc.common_out * o.close_brl, 0) + coalesce(sc.preferred_out * p.close_brl, 0)
           END AS market_cap_brl
    FROM sc2 sc LEFT JOIN (FROM px WHERE cls = 'ON') o USING (issuer_cnpj)
            LEFT JOIN (FROM px WHERE cls = 'PN') p USING (issuer_cnpj)
    WHERE o.close_brl IS NOT NULL OR p.close_brl IS NOT NULL
), m AS (
    SELECT issuer_cnpj, form, reference_date, metric, period_start, period_end, CAST(value_brl AS DOUBLE) AS v
    FROM fundamental_metric
    WHERE consolidation = 'con' AND received_on <= CAST(d AS DATE)
      AND metric IN ('net_income_controlling', 'equity_controlling', 'equity', 'noncontrolling_interest')
    QUALIFY row_number() OVER (
        PARTITION BY issuer_cnpj, metric, period_start, period_end ORDER BY received_on DESC, version DESC) = 1
), ytd AS (  -- year-to-date (or annual) earnings, one per period end
    SELECT issuer_cnpj, period_end, v, date_diff('month', period_start, period_end) >= 11 AS annual
    FROM m WHERE metric = 'net_income_controlling' AND month(period_start) = 1 AND day(period_start) = 1
), last_ytd AS (
    FROM ytd QUALIFY row_number() OVER (PARTITION BY issuer_cnpj ORDER BY period_end DESC) = 1
), ttm AS (
    SELECT l.issuer_cnpj, l.period_end AS earnings_period_end,
           CASE WHEN l.annual THEN l.v ELSE l.v + a.v - b.v END AS earnings_ttm
    FROM last_ytd l
    LEFT JOIN ytd a ON a.issuer_cnpj = l.issuer_cnpj AND a.annual
         AND a.period_end = make_date(year(l.period_end) - 1, 12, 31)
    LEFT JOIN ytd b ON b.issuer_cnpj = l.issuer_cnpj AND b.period_end = l.period_end - INTERVAL 1 YEAR
), bs AS (  -- the latest balance sheet: controlling equity as filed, else equity - non-controlling interest
    SELECT issuer_cnpj, period_end AS book_date,
           coalesce(max(v) FILTER (WHERE metric = 'equity_controlling'),
                    max(v) FILTER (WHERE metric = 'equity') - coalesce(max(v) FILTER (
                        WHERE metric = 'noncontrolling_interest'), 0)) AS book_value
    FROM m WHERE metric IN ('equity_controlling', 'equity', 'noncontrolling_interest')
    GROUP BY issuer_cnpj, period_end
), book AS (
    FROM bs QUALIFY row_number() OVER (PARTITION BY issuer_cnpj ORDER BY book_date DESC) = 1
)
SELECT CAST(d AS DATE) AS as_of, i.issuer_id, cap.issuer_cnpj, coalesce(i.trade_name, i.legal_name) AS issuer_name,
       cap.on_ticker, cap.on_close,
       cap.pn_ticker, cap.pn_close, cap.price_date, cap.common_out, cap.preferred_out, cap.shares_reference_date,
       cap.market_cap_brl, ttm.earnings_ttm, ttm.earnings_period_end, book.book_value, book.book_date,
       cap.market_cap_brl / nullif(ttm.earnings_ttm, 0) AS price_earnings,
       cap.market_cap_brl / nullif(book.book_value, 0) AS price_book
FROM cap
JOIN issuer i ON i.cnpj = cap.issuer_cnpj
LEFT JOIN ttm USING (issuer_cnpj)
LEFT JOIN book USING (issuer_cnpj)
"""


def fii_valuation_sql(s: Path) -> str:
    """`fii_valuation(d)`: per FII quota line, as known on `d` (ADR-0021 addendum). NAV per quota from the latest CVM
    monthly report delivered by `d` (`cvm_fii`, matched by the quota ISIN it states); the last standard-lot close in
    the 30 days to `d`; P/VP = close / NAV per quota; trailing dividend yield = income per quota with a data-com in
    the 12 months to `d` (Fundos.NET notices delivered by `d`) / close."""
    summ = _rp(s / "cvm_fii" / "monthly_summary" / "**" / "*.parquet")
    gen = _rp(s / "cvm_fii" / "monthly_general" / "**" / "*.parquet")
    return f"""
CREATE OR REPLACE MACRO fii_valuation(d) AS TABLE
WITH nav AS (
    SELECT g.isin, g.fund_name, s.reference_date AS nav_reference_date, g.delivered_on,
           CAST(s.nav_per_quota_brl AS DOUBLE) AS nav_per_quota
    FROM {summ} s JOIN {gen} g USING (cnpj, reference_date, version)
    WHERE g.delivered_on <= CAST(d AS DATE) AND g.isin IS NOT NULL AND s.nav_per_quota_brl > 0
    QUALIFY row_number() OVER (PARTITION BY g.isin ORDER BY s.reference_date DESC, s.version DESC) = 1
), line AS (
    SELECT i.instrument_id, i.value AS isin FROM instrument_identifier i WHERE i.scheme = 'ISIN'
), px AS (
    SELECT l.isin, arg_max(p.ticker, p.trade_date) AS ticker, max(p.trade_date) AS price_date,
           arg_max(CAST(p.close AS DOUBLE) * p.brl_num / p.brl_den, p.trade_date) AS close_brl
    FROM line l JOIN price_daily p USING (instrument_id)
    WHERE p.market_segment = 'lote_padrao'
      AND p.trade_date BETWEEN CAST(d AS DATE) - INTERVAL 30 DAY AND CAST(d AS DATE)
    GROUP BY l.isin
), dy AS (
    SELECT isin, sum(CAST(value_per_quota AS DOUBLE)) AS income_12m
    FROM fii_distribution
    WHERE kind = 'rendimento' AND base_date > CAST(d AS DATE) - INTERVAL 365 DAY AND base_date <= CAST(d AS DATE)
      AND (delivered_at IS NULL OR CAST(delivered_at AS DATE) <= CAST(d AS DATE))
    GROUP BY isin
)
SELECT CAST(d AS DATE) AS as_of, px.ticker, nav.isin, nav.fund_name, px.price_date, px.close_brl,
       nav.nav_per_quota, nav.nav_reference_date, nav.delivered_on AS nav_delivered_on,
       px.close_brl / nav.nav_per_quota AS price_to_nav, dy.income_12m,
       dy.income_12m / px.close_brl AS dividend_yield_12m
FROM nav JOIN px USING (isin) LEFT JOIN dy USING (isin)
"""


def build(z: Zones) -> list[str]:
    """(Re)create every view whose files exist. Returns the names created."""
    made: list[str] = []
    # not `catalog.duckdb.tmp`: that is DuckDB's own spill directory for `catalog.duckdb` (a killed query leaves it,
    # 38 GB on 2026-11-08; delete it when no query runs)
    tmp = z.catalog.with_name("catalog.building.duckdb")
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
        if {"share_count", "issuer", "issuer_instrument", "fundamental_metric", "adjustment_factor"} <= set(made):
            con.execute(VALUATION)
            made.append("valuation()")
        if {"instrument_identifier", "price_daily", "fii_distribution"} <= set(made) and (
            z.staging / "cvm_fii" / "monthly_summary"
        ).exists():
            con.execute(fii_valuation_sql(z.staging))
            made.append("fii_valuation()")
    finally:
        con.close()
    tmp.replace(z.catalog)
    return made
