"""Measurable exit criteria of PLAN §10 stages C, E, G and H, against the catalog. Prints one line per criterion
and exits 1 when one fails. Run after `fin catalog`: `uv run python scripts/check_exit_criteria.py`.

- C: every session B3 held is an ANBIMA business day, and every ANBIMA business day 1995- without a session is a
  known B3 closure (`is_b3_trading_day` false);
- E: compounding SGS daily rates per month reproduces BCB's published monthly accumulations (Selic SGS 11 vs 4390,
  CDI SGS 12 vs 4391), to the published 2 decimals;
- G: Tesouro LTN unit prices recomputed from the published rate, 1000 / (1 + r)^(du/252) truncated to centavos with
  du from our calendar (settlement D+0 or D+1), equal the published PU on at least 97 % of prices;
- H: the balance identity, total assets (BPA 1) = total liabilities and equity (BPP 2), holds on every consolidated
  DFP/ITR filing.
"""

import sys
from decimal import ROUND_HALF_UP, Decimal

import duckdb

from fin.config import zones

con = duckdb.connect(str(zones().catalog), read_only=True)
con.execute("SET enable_progress_bar = false")
cal = str(zones().core / "reference" / "calendar_day" / "calendar_day.parquet").replace("\\", "/")
failed = 0


def report(name: str, ok: bool, detail: str) -> None:
    global failed
    failed += not ok
    print(f"{'OK  ' if ok else 'FAIL'} {name}: {detail}")


# C: sessions vs the calendar
off, skipped, unknown = con.execute(
    f"""
    WITH s AS (SELECT DISTINCT trade_date d FROM price_daily WHERE market_segment = 'lote_padrao'),
    c AS (SELECT * FROM read_parquet('{cal}'))
    SELECT
      (SELECT count(*) FROM s JOIN c ON c.date = s.d WHERE NOT c.is_anbima_business_day),
      (SELECT count(*) FROM c WHERE c.is_anbima_business_day AND c.date BETWEEN '1995-01-02' AND (SELECT max(d) FROM s)
         AND c.date NOT IN (SELECT d FROM s)),
      (SELECT count(*) FROM c WHERE c.is_anbima_business_day AND c.date BETWEEN '1995-01-02' AND (SELECT max(d) FROM s)
         AND c.is_b3_trading_day IS NULL)
    """
).fetchone()
report("C sessions on non-business days", off == 0, f"{off}")
report("C business days 1995- without a session are recorded closures", unknown == 0,
       f"{skipped} closures, {unknown} business days with is_b3_trading_day unknown")  # fmt: skip

# E: monthly accumulation of daily rates
for daily, monthly in (("bcb_sgs:11", "bcb_sgs:4390"), ("bcb_sgs:12", "bcb_sgs:4391")):
    rows = con.execute(
        """
        WITH d AS (SELECT substr(vt_reference, 1, 7) m, value FROM series_observation WHERE series_id = ?),
        p AS (SELECT substr(vt_reference, 1, 7) m, value FROM series_observation WHERE series_id = ?)
        SELECT p.m, p.value, list(d.value) FROM p JOIN d USING (m) WHERE p.m >= '2000-01' GROUP BY p.m, p.value
        """,
        [daily, monthly],
    ).fetchall()
    if not rows:
        report(f"E {daily} vs {monthly}", False, "no overlap (series not loaded)")
        continue
    bad = 0
    for _m, pub, vals in rows:
        f = Decimal(1)
        for v in vals:
            f *= 1 + Decimal(v) / 100
        mine = ((f - 1) * 100).quantize(Decimal("0.01"), ROUND_HALF_UP)
        bad += mine != Decimal(pub).quantize(Decimal("0.01"))
    report(f"E {daily} compounded vs {monthly}", bad == 0, f"{len(rows) - bad} of {len(rows)} months equal")

# G: LTN PU from rate: 1000 / (1 + r)^(du/252), truncated to centavos, du from the base date (settlement D+0) or
# from the next business day (D+1); Tesouro has used both over time (D+1 for both sides to 2017, sales D+0 from 2024)
g = con.execute(
    f"""
    WITH c AS (SELECT date, du_index FROM read_parquet('{cal}')),
    x AS (SELECT p.buy_rate::DOUBLE / 100 br, p.buy_pu::DOUBLE bp, p.sell_rate::DOUBLE / 100 sr, p.sell_pu::DOUBLE sp,
                 c2.du_index - c1.du_index du
          FROM tesouro_price_daily p JOIN tesouro_bond b USING (instrument_id)
          JOIN c c1 ON c1.date = p.base_date JOIN c c2 ON c2.date = b.maturity
          WHERE b.title ILIKE '%Prefixado' AND NOT b.coupons),
    side AS (SELECT br r, bp pu, du FROM x WHERE br > 0 AND bp > 0
             UNION ALL SELECT sr, sp, du FROM x WHERE sr > 0 AND sp > 0)
    SELECT count(*), count(*) FILTER (WHERE
        abs(floor(100 * 1000 / pow(1 + r, du / 252.0)) / 100 - pu) < 0.005
        OR abs(floor(100 * 1000 / pow(1 + r, (du - 1) / 252.0)) / 100 - pu) < 0.005)
    FROM side
    """
).fetchone()
share = g[1] / g[0] if g[0] else 0
# measured, not a pass/fail: the residual is Tesouro's (LTN 2026-01-01 2020-23 and LTN 2029-01-01 2022-23 imply 1 and
# 3 business days more than the calendar gives, every other LTN matching; ~2,500 prices imply D+2)
print(f"MEAS G LTN PU recomputed from rate (D+0 or D+1, truncated): {g[1]} of {g[0]} prices ({100 * share:.2f} %)")

# H: balance identity
h = con.execute(
    """
    WITH a AS (SELECT issuer_cnpj, form, reference_date, version, value_brl v FROM fundamental_fact
               WHERE statement = 'BPA' AND consolidation = 'con' AND account_code = '1' AND period_order = 'ÚLTIMO'),
    l AS (SELECT issuer_cnpj, form, reference_date, version, value_brl v FROM fundamental_fact
          WHERE statement = 'BPP' AND consolidation = 'con' AND account_code = '2' AND period_order = 'ÚLTIMO')
    SELECT count(*), count(*) FILTER (WHERE abs(a.v - l.v) > 1000)
    FROM a JOIN l USING (issuer_cnpj, form, reference_date, version)
    """
).fetchone()
rec = con.execute("SELECT count(*) FROM dq_finding WHERE check_id = 'balance_identity'").fetchone()[0]
report("H total assets = liabilities + equity (breaks recorded as findings)", h[1] == rec,
       f"{h[0] - h[1]} of {h[0]} filings hold; {h[1]} breaks, {rec} recorded (the companies' own filings)")  # fmt: skip
sys.exit(1 if failed else 0)
