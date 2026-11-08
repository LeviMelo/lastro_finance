## ADR-0024: The calendar before 2001 is BCB's CDI publication days, marked as such

**Date:** 2026-11-08. **Status:** active. Settles OQ-22. `fin/reference/calendar.py` (`extend_back`), built by
`ingest/anbima_calendar.build_calendar` (called by the ANBIMA calendar and by BCB SGS).

**Context.** ANBIMA's holiday file starts in 2001. Prices start in 1986, and accrual (CDI, Selic, VNA) needs
business days before 2001. No official holiday list for 1986-2000 was found. BCB's SGS 12 (CDI) is published on
every business day from 1986-03-06. Over 2001-2005 its dates equal ANBIMA's business days exactly (1,259 days,
0 differences; docs/sources/bcb_sgs.md).

**Decision.**
- `calendar_day` starts on 1986-03-06. Before 2001 a business day is a day SGS 12 was published.
- Those rows have `basis` = `bcb_sgs_12` and no holiday names; ANBIMA's rows have `basis` = `anbima`.
- `du_index` runs on continuously across the seam.

**Measured.** 5,415 dates before 2001, 3,684 of them business days. The 2001-01-02 seam is continuous.

**Addendum (same day).**
- A B3 session before 2001 is a business day too: BCB skipped CDI publication on 1986-03-07, 11 and 13 (after the
  Plano Cruzado) while B3 traded.
- `is_b3_trading_day` is filled from observed standard-lot sessions between the first and the last session. 104
  business days since 1995 had no session (OQ-1).
