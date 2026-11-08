"""Golden corporate-event cases (docs/sources/golden_events.md) against core.corporate_event, via the catalog.

Run after `fin catalog`: `uv run python scripts/check_golden_events.py`. Exits 1 when a case is missing.
"""

import datetime as dt
import sys

import duckdb

from fin.config import zones

con = duckdb.connect(str(zones().catalog), read_only=True)
missing = 0
cases = [
    ("ITUB4", "BONUS", "2025-12-26", 103, 100),
    ("ITUB4", "BONUS", "2025-03-18", 11, 10),  # B3 misses it; Yahoo has it
    ("SLCE3", "BONUS", "2026-01-02", 9, 8),
    ("RADL3", "BONUS", "2025-12-23", 51, 50),
    ("EGIE3", "BONUS", "2025-11-27", 7, 5),
    ("BHIA3", "REVERSE_SPLIT", "2023-12-15", 1, 25),
]
for tk, typ, ex, n, d in cases:
    rows = con.execute(
        """
        select e.event_type, e.data_com, e.ex_date, e.ratio_num, e.ratio_den, e.sources,
               round(e.price_check, 3), e.status
        from corporate_event e
        join instrument_identifier i on i.instrument_id = e.instrument_id and i.scheme = 'TICKER' and i.value = ?
        where e.ex_date between ? and ? and e.ratio_num is not null
        """,
        [tk, dt.date.fromisoformat(ex) - dt.timedelta(days=5), dt.date.fromisoformat(ex) + dt.timedelta(days=5)],
    ).fetchall()
    ok = any(r[2] == dt.date.fromisoformat(ex) and (r[3], r[4]) == (n, d) for r in rows)
    print("OK " if ok else "MISS", tk, typ, ex, f"{n}:{d}", rows)
    missing += 0 if ok else 1
cash = con.execute(
    """
    select e.event_type, e.data_com, e.ex_date, sum(e.cash_per_share)
    from corporate_event e join instrument_identifier i on i.instrument_id = e.instrument_id
     and i.scheme = 'TICKER' and i.value = 'GRND3'
    where e.data_com = '2025-12-26' group by all
    """
).fetchall()
print("GRND3 2025-12-26 cash (golden sum 1.086264641):", cash)
# the IPE filing that proves each ITUB bonus (golden_events.md rows 1 and 1b)
for ex, protocol in (
    ("2025-12-26", "019348IPE181220250198198217-32"),
    ("2025-03-18", "019348IPE050220250104569311-22"),
):
    got = con.execute(
        """
        select e.ipe_protocol from corporate_event e join instrument_identifier i on i.instrument_id = e.instrument_id
         and i.scheme = 'TICKER' and i.value = 'ITUB4'
        where e.ex_date = ? and e.ratio_num is not null
        """,
        [dt.date.fromisoformat(ex)],
    ).fetchall()
    proven = any(r[0] == protocol for r in got)
    print("OK " if proven else "MISS", "ITUB4", ex, "IPE", protocol, got)
    missing += 0 if proven else 1
ok_cash = bool(cash) and str(cash[0][3]).startswith("1.086264641")
print("OK " if ok_cash else "MISS", "GRND3 cash sum")
sys.exit(1 if missing or not ok_cash else 0)
