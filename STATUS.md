# STATUS.md

What is true now. Rewritten in place, never appended; history is in git. Last rewritten 2026-11-08.

## Where the project is

Day two (2026-11-08). The data layer (stages A–H) is built and measured; the dossier (L) and portfolio analytics
(K) exist on a portfolio file; the ledger (I) waits for the owner's documents.
- **Scope and terms** (ADR-0011, ADR-0012): stocks, FIIs, ETFs and Tesouro Direto from 2026; context data as its own
  domain; collection for personal use, never redistributed; request limits per source and adaptive (ADR-0023).
- **PLAN.md is a prior, not a contract:** where measured data contradicts it, the evidence is followed and recorded.
- **Exit criteria** (`scripts/check_exit_criteria.py`, docs/evaluation/2026-11-08-exit-criteria.md):
  - pass: C (calendar against B3 sessions), E (Selic and CDI compounding 323/323 months), F (look-through 0.0003 %;
    CVM 175 bridge 19,971/20,217, ADR-0025) and H (balance identity, the 6 breaks being the companies' own filings;
    point in time across restatements 21/21 on versions recovered from RAD, ADR-0027);
  - measured: G, LTN PU from rate 93.06 % (the rest are Tesouro's own irregularities).
- **Golden checks:** 9 corporate-event cases exact; the §13.1 portfolio returns +37.38 % (plan +37.2 %).
- **Data quality** (ADR-0022): `fin quality` runs 15 named checks into `dq_finding` (1,437 findings, none open), every
  finding decided by rule or review; sessions with an out-of-range open/close are kept as B3 prints them (6 COTAHIST
  rows quarantined, of 25 M). Completeness is measured: cash events against Yahoo (99.5 %), daily series gaps, CVM 175 quota breaks.
- **Storage** (ADR-0014): raw 9.0 GB, staging 5.2 GB, core 0.2 GB; C: has 42 GB free.

## What the data layer holds

- **Exchange-traded:** COTAHIST prices 1986– (8,464 instruments, identity through ISIN and ticker changes, 260
  links); corporate events 52,645 (every stock event decided; quote-basis changes, spin-offs, implied events,
  payouts proven by CVM filings; ADR-0016); adjusted prices on read; B3 Price Report from 2026-10-19.
- **Companies:** CVM DFP/ITR 2010– (66.8 M lines) plus superseded versions from RAD (backfill running: XML era
  2021–, then the legacy layout 2010–21; ADR-0027); FRE share counts and treasury 2010–; FCA securities; IPE
  filings index 2003–; issuers 4,006 (companies and funds); valuation by date 2010–; insider trades and holdings by
  role group 2018– (VLMO, 419,707 lines; free text naming people is not parsed).
- **Funds:** daily NAV 2000– (82 M rows), CDA holdings 2005– (101 M positions), FII reports 2016–, FIAGRO 2025–,
  fund register and CVM 175 lineage (27,461 classes), FII payouts 2016– (40,490); ETF NAV per quota from
  Fundos.NET 2018– plus CVM 2004–18, linked to the quota by trading name and checked by price (ADR-0029; backfill of
  225,340 daily reports running, then 8,128 monthly ETF portfolios). Fixed-income ETFs have no COTAHIST prices.
- **Fixed income:** Tesouro Direto 2004–, VNA 2000–, ANBIMA bond rates 2020– (mirror, verified against ANBIMA),
  B3 reference-rate curves 2001–, B3 OTC fixed-income trades 2023-03– (18.5 M), SND daily debenture PU 1994–
  (7.5 M rows), BDI debenture business (rolling window).
- **Rates, FX and context:** BCB SGS (CDI, Selic, monthly accumulations), PTAX 10 currencies 1984–, Focus 2000–,
  Copom, SIDRA, Ipeadata, futures 2018– (mirror), ANBIMA IMA indices 2001– (ADR-0030), ETTJ month-end 2015– (SUSEP
  copy) and daily from 2026-10, VNA/projections, NEFIN factors, global rates, VIX,
  commodities, OECD, CFTC; calendar 1986– (ADR-0024).
- **Ephemeral sources** are archived by `fin ingest daily` (run by hand on 2026-11-07 and 2026-11-08, 0 errors).
- **Dossier** (ADR-0026): `fin export dossier` with holdings (stocks, FIIs, ETFs, Tesouro Direto), valuation, performance, risk, sector exposure, events,
  fundamentals and quality findings.

## Not done

- **Blocked by the harness:** the Windows scheduled task, and any in-session loop, are refused as persistence:
  `fin ingest daily` runs by hand; a day not run is lost for the today-only sources.
- **The owner's documents** for the ledger (Stage I) in `inbox/`.
- **Owner decisions:** B3 PR history 2018– (OQ-20, deferred); B3 HistoricoRF aggregate files (a form with a
  reCAPTCHA field); ANBIMA debenture history and ANBIMA Data (login); FRED/Tiingo tokens (OQ-23); paid sources (OQ-10).

## Next (engineering)

1. RAD restatement backfill: ~6,800 superseded versions left at ~410/h (a session-free client: ASP.NET had
   serialised the 4 workers), then `fin reparse cvm_rad_versions` and the H check again.
2. ETF NAV and CDA backfills to completion; `etf_link` measured on full data; ETF look-through from the CDA.
3. ANBIMA routes with no free history (daily ETTJ, bond rates before 2020, VNA, projections): notes; projections
   need a slow Wayback fetch.
