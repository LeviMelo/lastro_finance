## ADR-0032: Models read a monthly point-in-time panel; fundamental metrics live in the derived zone

**Date:** 2026-11-08. **Status:** active. `export/panel.py` (`fin export panel`), `catalog.py`
(`fundamental_metric`).

**Context.** The owner wants the data layer to plug into "some model" without knowing which yet. Models read one
tidy table of assets by dates, not twenty catalog views. Computing fundamentals as known at each date was too slow:
`valuation(d)` took 49 s per date, because the metrics were re-derived from 66 M statement lines on every call.

**Decision.**
- **The panels.** `fin export panel` writes `data/exports/panel/`:
  - `equity_monthly.parquet`: one row per B3 share or unit and month with a standard-lot session, delisted lines
    included (point-in-time universe). It carries returns (total and price, from raw closes and the derived
    factors), momentum 12-1, 12-month volatility, trailing dividend yield, liquidity, issuer and sector, and
    `valuation(month_end)`: market cap, P/E, P/B, earnings and book, as known that day.
  - `macro_monthly.parquet`: CDI, Selic, IPCA, IGP-M, IBC-Br, Ibovespa, PTAX, Fed funds, US 10-year.
  - `README.md`: every column with meaning and unit.
- **No shifting.** Characteristics of month t use data up to its month end; the panel shifts nothing, so a model
  decides its own lags.
- **Suspect returns.** A month's total return beyond 4x either way is flagged `ret_suspect` (79 of 82,227), not
  dropped (invariant 11).
- **Materialized metrics.** `fundamental_metric` is materialized at `derived/fundamental_metric` (1.2 M rows,
  17 MB), rebuilt by `fin catalog` whenever a statement file is newer. `valuation(d)` now takes 0.4 s, and the
  2010–2026 panel builds in about 3 minutes.

**Measured (2026-11-08).** 85,932 rows of 1,160 lines, 2010-01 → 2026-11. Coverage:

| Column | 2010 | 2011 | 2014 | 2022 onward |
|---|---|---|---|---|
| Issuer link | 96 % | 97 % | 99 % | 99 % |
| Market cap | 3 % | 47 % | 78 % | ~91 % |
| P/B | 0 % | 36 % | 69 % | ~83 % |

Fundamentals start in 2011 because CVM's first open-data statements (fiscal 2010) were delivered then.

**Would overturn it.** A model that needs daily frequency (a daily panel is the same SQL with a different grid), or
storage pressure on the derived zone.
