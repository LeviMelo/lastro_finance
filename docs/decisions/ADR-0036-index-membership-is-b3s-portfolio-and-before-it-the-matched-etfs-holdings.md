## ADR-0036: Index membership is B3's portfolio, and before it the holdings of the ETF matched to the index

**Date:** 2026-11-09. **Status:** active. `core/indices.py`; core `etf_index`, `index_member`; built by
`b3_bdi_pdf`'s derive step.

**Context.**
- B3's daily bulletin gives every index's portfolio from 2022-03 (ADR-0034); no B3 route goes earlier
  (b3_index_portfolio.md).
- The ETFs' monthly portfolios go back to 2018-06 (Fundos.NET CDA, ADR-0030). Which ETF tracks which index is in no
  field, and a ticker-to-index table written from memory is not evidence.

**Decision.**
- **The match is measured.** Each month both exist, an ETF's equity tickers are compared with every index's tickers
  on the month's last bulletin. The ETF is matched to the index whose Jaccard similarity is at least 0.90 in 80 % of
  the months compared (`etf_index`).
  - Measured on 2026-02→10: 31 matches, median similarity 0.95–1.0. BOVA11, BOVV11 and XBOV11 match IBOVESPA;
    SMAL11 matches SMLL; PIBB11 IBRX50; BRAX11 IBXX; ISUS11 ISE; ECOO11 ICO2; GOVE11 IGCT; MATB11 IMAT.
- **Membership** (`index_member`, one row per index, month and ticker):
  - from the bulletin's first month: B3's portfolio in force on the month's last bulletin (`source` = `b3_bdi`);
  - before it: the holdings of the best-matched ETF that reported that month (`source` = `etf_cda`, `fund_cnpj`
    names it).
- **Names.** IBrX 100 is printed "IBXX" in most bulletins and "IBRX" in some; both are kept as IBXX.

**Consequences.**
- Point-in-time membership of the main indices from 2018 (Ibovespa, SMLL, IBrX-50, IBrX-100, ISE, ICO2, IGCT,
  IMAT); the other indices from 2022-03.
- `etf_cda` rows are a proxy. An ETF can hold a name outside its index (a pending inclusion, a leftover) or miss
  one inside it. Weights come only from B3's rows.
- Indices without a tracking ETF (IFIX, IDIV, ITAG…) start in 2022-03.
