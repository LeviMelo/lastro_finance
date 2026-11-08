## ADR-0026: The dossier is built now, from a portfolio file, until the ledger exists

**Date:** 2026-11-08. **Status:** active. `fin export dossier --portfolio <toml> --as-of <date>`
(`fin/export/dossier.py`).

**Context.** PLAN §8's dossier is built from holdings, and holdings come from the ledger (Stage I). The ledger needs the
owner's brokerage notes and B3 Área do Investidor exports, which are not in `inbox/` yet. The rest of the dossier
(valuation, performance, events, fundamentals, data quality) already has its data.

**Decision.**
- The dossier reads a TOML portfolio (`[holdings]` ticker = quantity; optional `[performance] since`). When the
  ledger exists it will replace the file as the source of positions; the sections stay.
- Output goes to `data/exports/dossier-<as-of>/`: `dossie.md` (pt-BR) plus Parquet tables (holdings, performance,
  upcoming, fundamentals, findings).
- Every figure carries its date and method:
  - prices are the last COTAHIST close, flagged as stale after 7 days;
  - returns come from `price_adjusted`, buy-and-hold weighted by start values;
  - fundamentals come from `valuation(d)`;
  - the data-quality findings touching a holding are listed with their status.
- A holding the system cannot price is listed and labeled, never dropped.

**Measured.** On `examples/portfolio_reference.toml` (the §13.1 portfolio, R$ 100,000 at the 2025-10-02 closes), the
dossier gives total return +37.36 % and price return +28.68 % to 2026-10-16, as the golden check does.

**Addendum (same day): risk and exposure** (`analytics/risk.py`). These are descriptive statistics of the realised
buy-and-hold path, labeled as not being forecasts:
- annualised volatility of daily log returns;
- maximum drawdown with its dates;
- beta to the Ibovespa;
- weights by the issuers' CVM sector.

On the sample: volatility 16.50 %, drawdown −15.50 % (2026-04-13 to 2026-08-14), beta 0.82.
