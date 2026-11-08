"""Golden integration test of PLAN §4.8.4 / §13.1: the 17-stock reference portfolio, buy-and-hold, 2025-10-02 to
2026-10-16, against the plan's Yahoo-based estimate (total +37.2 %, price +28.5 %, Ibovespa +42.4 %, CDI +14.9 %).

Run after `fin catalog`: `uv run python scripts/check_golden_portfolio.py`. Exits 1 when a figure is outside its
tolerance (TOLERANCE_PP percentage points). Each line's total return is close_adjusted (splits, spin-offs and cash,
reinvested at the ex-date close) at the end over the start; its price return uses splits and spin-offs only.
"""

import sys
from datetime import date
from decimal import Decimal

import duckdb

from fin.config import zones

START, END = date(2025, 10, 2), date(2026, 10, 16)
WEIGHTS = {
    "VALE3": 3.0, "PETR4": 6.5, "WEGE3": 5.4, "ITUB3": 6.0, "B3SA3": 6.0, "LREN3": 5.6, "GRND3": 5.0, "RADL3": 5.7,
    "EGIE3": 5.7, "HYPE3": 6.8, "FLRY3": 6.1, "ABEV3": 5.3, "PSSA3": 7.0, "SLCE3": 5.6, "AGRO3": 5.9, "MDIA3": 5.4,
    "PRIO3": 5.8,
}  # fmt: skip
PLAN = {"total": 37.2, "price": 28.5, "ibovespa": 42.4, "cdi": 14.9}
TOLERANCE_PP = 2.0  # the plan's figures are an estimate from Yahoo adjusted closes; weights renormalized from 96.8 %

con = duckdb.connect(str(zones().catalog), read_only=True)
con.execute("SET enable_progress_bar = false")
w_sum = sum(WEIGHTS.values())
tot = price = 0.0
print(f"{'ticker':7} {'weight':>6} {'total %':>8} {'price %':>8}  events in the window")
for tk, w in WEIGHTS.items():
    rows = con.execute(
        """
        WITH line AS (
            SELECT i.instrument_id FROM instrument_identifier i
            WHERE i.scheme = 'TICKER' AND i.value = ? AND i.vt_from <= ? AND i.vt_to >= ?
        )
        SELECT a.trade_date, a.close_adjusted, a.close_split_adjusted
        FROM price_adjusted a JOIN line USING (instrument_id)
        WHERE a.trade_date IN (
            (SELECT max(trade_date) FROM price_adjusted JOIN line USING (instrument_id) WHERE trade_date <= ?),
            (SELECT max(trade_date) FROM price_adjusted JOIN line USING (instrument_id) WHERE trade_date <= ?))
        ORDER BY a.trade_date
        """,
        [tk, END, START, START, END],
    ).fetchall()
    if len(rows) != 2:
        print(f"{tk:7} MISSING prices {rows}")
        sys.exit(1)
    (_, a0, s0), (_, a1, s1) = rows
    rt, rp = a1 / a0 - 1, s1 / s0 - 1
    ev = con.execute(
        """
        SELECT string_agg(e.event_type || ' ' || e.ex_date || coalesce(' ' || e.ratio_num || ':' || e.ratio_den, ''),
                          '; ' ORDER BY e.ex_date)
        FROM corporate_event e JOIN instrument_identifier i ON i.instrument_id = e.instrument_id
         AND i.scheme = 'TICKER' AND i.value = ?
        WHERE e.ex_date > ? AND e.ex_date <= ? AND e.ratio_num IS NOT NULL
          AND e.status IN ('confirmed', 'price_only', 'official')
        """,
        [tk, START, END],
    ).fetchone()
    tot += w / w_sum * rt
    price += w / w_sum * rp
    print(f"{tk:7} {w:6.1f} {100 * rt:8.2f} {100 * rp:8.2f}  {ev[0] if ev and ev[0] else ''}")


def level(series: str, d: date) -> float:
    r = con.execute(
        "SELECT value FROM series_observation WHERE series_id = ? AND vt_reference <= ? ORDER BY vt_reference DESC "
        "LIMIT 1",
        [series, d.isoformat()],
    ).fetchone()
    return float(r[0])


ibov = level("ipeadata:GM366_IBVSP366", END) / level("ipeadata:GM366_IBVSP366", START) - 1
cdi_rows = con.execute(
    "SELECT value FROM series_observation WHERE series_id = 'bcb_sgs:12' AND vt_reference > ? AND vt_reference <= ?",
    [START.isoformat(), END.isoformat()],
).fetchall()
f = Decimal(1)
for (v,) in cdi_rows:
    f *= 1 + Decimal(v) / 100
cdi = float(f) - 1
got = {"total": 100 * tot, "price": 100 * price, "ibovespa": 100 * ibov, "cdi": 100 * cdi}
bad = 0
for k, v in got.items():
    ok = abs(v - PLAN[k]) <= TOLERANCE_PP
    bad += not ok
    print(f"{'OK ' if ok else 'MISS'} {k:9} {v:7.2f} %  (plan {PLAN[k]:.1f} %, tolerance {TOLERANCE_PP} pp)")
sys.exit(1 if bad else 0)
