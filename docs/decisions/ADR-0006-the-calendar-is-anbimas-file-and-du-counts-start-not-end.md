## ADR-0006: The calendar is built from ANBIMA's holidays file alone; du counts business days in [start, end)

**Date:** 2026-11-07. **Status:** active.

**Context.** PLAN §4.1 invariant 9 and §4.9. ANBIMA's `feriados_nacionais.xls` lists 1,264 national holidays from
2001-01-01 to 2099-12-25, weekend holidays included (docs/sources/anbima_calendar.md). BCB publishes CDI (SGS 12) for
every business day, and its Calculadora do Cidadão gives accumulated CDI factors (docs/sources/bcb_sgs.md).

**Decision.**
- A business day is a weekday not listed in the latest fetched version of ANBIMA's file; `calendar_version` is that
  file's SHA-256. Earlier versions stay in staging.
- `du_index` = business days strictly before the date; `du(a, b) = du_index[b] − du_index[a]` counts [a, b).
- Dates outside 2001-01-01…2099-12-31 raise; the calendar never extrapolates.
- `is_b3_trading_day` stays null until B3 sessions are observed (OQ-1).

**Evidence.** CDI's publication dates over 2024-01-02…2025-01-10 are exactly the calendar's business days, and BCB's
factors 1.02621059 (2024-01-02→2024-04-01) and 1.10875983 (2024-01-02→2025-01-02) reproduce exactly as the product over
[start, end), rounded half-up to 8 places (`tests/unit/test_calendar.py`).

**What would reverse it.** A published DU count or factor the calendar fails to reproduce, or a need for business days
before 2001 (older bonds), which would require another holiday source.
