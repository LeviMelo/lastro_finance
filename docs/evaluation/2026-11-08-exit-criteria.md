# Exit criteria of stages C, E, G, H (PLAN §10), 2026-11-08

`scripts/check_exit_criteria.py`, against the catalog.

| criterion | result |
|---|---|
| C: sessions only on business days | 0 off (3 in 1986-03 before BCB published CDI daily: now business days) |
| C: business days without a session are recorded closures | 104 since 1995, `is_b3_trading_day` filled from observed sessions |
| E: Selic SGS 11 compounded = SGS 4390 | 323 of 323 months (2000-) |
| E: CDI SGS 12 compounded = SGS 4391 | 323 of 323 months (SGS 4391 added) |
| G: LTN PU from rate | 52,652 of 56,580 prices (93.06 %) |
| H: assets = liabilities + equity | 24,322 of 24,328 filings; the 6 breaks are the companies' own filings (check `balance_identity`) |

**G.** The formula is 1000 / (1 + r)^(du/252), truncated to centavos, with `du` counted from settlement. Both sides
settled D+1 to 2017; from 2024 sales settle D+0 and purchases D+1; 2018-2023 is mixed. Of the residual:
- 1,416 prices are two bonds, LTN 2026-01-01 (2020-23) and LTN 2029-01-01 (2022-23), whose buy PU implies 1 and 3
  more business days, while every other LTN matches;
- about 2,500 prices imply D+2 settlement.

So G is measured, not passed: the published prices stand.
