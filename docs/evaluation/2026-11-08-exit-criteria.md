# Exit criteria of stages C, E, G, H (PLAN §10), 2026-11-08

`scripts/check_exit_criteria.py`, against the catalog.

| criterion | result |
|---|---|
| C: sessions only on business days | 0 off (3 in 1986-03 before BCB published CDI daily: now business days) |
| C: business days without a session are recorded closures | 104 since 1995, `is_b3_trading_day` filled from observed sessions |
| E: Selic SGS 11 compounded = SGS 4390 | 323 of 323 months (2000-) |
| E: CDI SGS 12 compounded = SGS 4391 | 323 of 323 months (SGS 4391 added) |
| G: LTN PU from rate | 52,652 of 56,580 prices (93.06 %) |
| H: assets = liabilities + equity | 24,813 of 24,819 filings; the 6 breaks are the companies' own filings (check `balance_identity`) |
| H: point in time across restatements | 21 of 21 restated filings (total assets changed, superseded version from RAD) give the original before the re-filing and the restatement after |
| F: look-through, sample fund | 07.593.972/0001-86, 2026-06: holdings R$ 291,170,747,079 vs NAV 291,169,931,166 (0.0003 %) |
| F: CDA net assets = daily report | 24,868 of 25,256 funds within 1 % (2026-06) |

**G.** The formula is 1000 / (1 + r)^(du/252), truncated to centavos, with `du` counted from settlement. Both sides
settled D+1 to 2017; from 2024 sales settle D+0 and purchases D+1; 2018-2023 is mixed. Of the residual:
- 1,416 prices are two bonds, LTN 2026-01-01 (2020-23) and LTN 2029-01-01 (2022-23), whose buy PU implies 1 and 3
  more business days, while every other LTN matches;
- about 2,500 prices imply D+2 settlement.

So G is measured, not passed: the published prices stand.

**H, restatements.** CVM's zips keep only the latest version of each filing: 6,137 filings show version 2 to 9, and
their earlier versions are gone from open data. From the archive's start (2026-11-07) every version is kept, and the
superseded ones are recovered from RAD (ADR-0027). Re-run 2026-11-08 with the RAD backfill in progress: 3,410 filings
held in two or more versions, 21 of them with a changed consolidated total assets and a later delivery; for all 21 the
as-of query returns version 1 the day before the re-filing and version 2 from it. The rule is also unit-tested
(`test_restated_statement_is_used_only_from_its_delivery`).

**Re-run 2026-11-09, RAD backfill complete.** Every superseded version RAD serves is held: 12.56 M statement lines, with
only document 67723 failing on CVM's side.
- Point in time: 506 of 506 restated filings give the original before the re-filing and the restatement from it. A
  version superseded on the day it arrived is excluded from the expectation (43185362000107 ITR 2013-Q1: v2 typed in
  units, v3 the same day), because no query on that day returns it.
- Balance identity: 29,399 of 29,408 filings hold. All 9 breaks are the companies' own filings, now recorded by
  `balance_identity`, which reads the RAD versions too.

**F, look-through.** Across funds, holdings sum to within 5 % of net assets for 90.6 % (median ratio 1.0013); the rest
hold receivables, payables, derivatives or confidential positions that CDA does not list.
