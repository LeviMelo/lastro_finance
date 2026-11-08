# STATUS.md

What is true now. Rewritten in place, never appended; history is in git. Last rewritten 2026-11-08.

## Where the project is

Day two (2026-11-08). The data layer (stages A–H) is built and measured; the dossier (L) and portfolio analytics
(K) exist on a portfolio file; the ledger (I) waits for the owner's documents.
- **Scope and terms** (ADR-0011, ADR-0012): stocks, FIIs, ETFs and Tesouro Direto from 2026; context data as its own
  domain; collection for personal use, never redistributed; request limits per source and adaptive (ADR-0023).
- **PLAN.md is a prior, not a contract:** where measured data contradicts it, the evidence is followed and recorded.
- **Exit criteria** (`scripts/check_exit_criteria.py`, docs/evaluation/2026-11-08-exit-criteria.md):
  - pass:
    - C: calendar against B3 sessions;
    - E: Selic and CDI compounding, 323/323 months;
    - F: look-through 0.0003 %; CVM 175 bridge 19,971/20,217 (ADR-0025);
    - H: balance identity, the 6 breaks being the companies' own filings; point in time across restatements,
      21/21 on versions recovered from RAD (ADR-0027);
  - measured: G, LTN PU from rate 93.06 % (the rest are Tesouro's own irregularities).
- **Golden checks:** 9 corporate-event cases exact; the §13.1 portfolio returns +37.38 % (plan +37.2 %).
- **Data quality** (ADR-0022):
  - `fin quality` runs 16 named checks into `dq_finding`; every finding is decided by rule or review.
  - Quarantine is for broken rows only. Real data a rule rejected is kept and reported instead: COTAHIST
    out-of-range sessions, formatted CNPJs, zero ETF quotas.
- **Storage** (ADR-0014, ADR-0031):
  - raw 11 GB, staging 5.9 GB, core 0.25 GB; C: has 36 GB free;
  - the Price Report history adds ~3 GB when done;
  - DuckDB connections cap temp files at 4 GB (a view once spilled 38 GB).

## What the data layer holds

- **Exchange-traded:**
  - COTAHIST prices 1986– (8,469 instruments, identity through ISIN and ticker changes);
  - corporate events 52,933 (every stock event decided; near-duplicates resolved against the price move; regroupings on lines Yahoo lacks proven by CVM filings or
    exact ratios; ADR-0016), adjusted prices on read;
  - B3 Price Report 2018– (backfill running, kept as tar+zstd at ~3 MB a day, ADR-0031): settlements, open interest,
    options and the fixed-income ETFs COTAHIST omits;
  - B3's listed funds (daily).
- **Companies:**
  - issuers linked to their shares through B3 roots, FCA codes, the ISIN issuer code, B3's ISIN registry and name
    history: 1,177 of 1,204 share and unit lines trading since 2010; unlinked volume ~0 from 2013 (ADR-0018);
  - CVM DFP/ITR 2010– plus superseded versions from RAD (backfill running at ~650/h, ~6 h left);
  - FRE share counts and treasury, FCA, IPE 2003–;
  - insider trades by role group (VLMO 2018–, 419,707 lines);
  - valuation by date.
- **Funds:**
  - daily NAV 2000– and CDA holdings 2005– (CVM), FII reports and payouts 2016–;
  - ETF NAV 2004– (Fundos.NET 2018–, CVM before): 244,939 reports of 263 funds, 218 verified links to their quotas
    (ADR-0029);
  - ETF monthly portfolios 2018– (453,397 positions) for look-through.
- **Fixed income:**
  - Tesouro Direto 2004–, VNA 2000–;
  - ANBIMA bond rates 2020– (mirror), IMA indices 2001–;
  - B3 curves 2001–, B3 OTC trades 2023-03–;
  - SND debenture PU 1994– and terms.
- **Rates, FX and context:**
  - BCB SGS, PTAX 1984–, Focus, Copom, SIDRA, Ipeadata;
  - ETTJ month-end 2015– (SUSEP copy);
  - FRED 28 series, with ALFRED vintages of 7 revisable US series (versions by release date);
  - Tiingo daily prices of 17 US benchmarks and Brazilian ADRs 1993–;
  - crypto daily klines (Binance, tier S);
  - NEFIN, global rates, commodities, OECD, CFTC;
  - calendar 1986– (ADR-0024).
- **Model panels** (ADR-0032): `fin export panel`, monthly point-in-time equity (85,932 rows, 2010–) and macro
  panels with a column dictionary; fundamentals from 2011 (CVM's first statements).
- **Dossier** (ADR-0026): holdings (stocks, FIIs, ETFs incl. fixed-income, Tesouro Direto), valuation,
  performance, risk with ETF look-through, events, fundamentals, quality findings.

## Not done

- **Blocked by the harness:** the Windows scheduled task and any in-session loop are refused as persistence.
  `fin ingest daily` runs by hand; a day not run is lost for the today-only sources.
- **The owner's documents** for the ledger (Stage I) in `inbox/`.
- **Owner decisions:**
  - B3 HistoricoRF aggregate files (a form with a reCAPTCHA field);
  - ANBIMA Data (login);
  - paid sources (OQ-10).
- **Measured as closed:**
  - ANBIMA daily ETTJ, bond rates before 2020, VNA and projections history;
  - B3 futures before 2018;
  - CVM fundamentals before 2010.

## Next (engineering)

1. RAD and PR backfills to completion (PR resumed after a nested-zip layout on 2023-07-19); then `fin reparse cvm_rad_versions`, the H check and the PR-based fixed-income
   ETF links on full history.
2. Index composition history from the ETF portfolios (gap matrix row 10).
3. Panel month-returns still flagged `ret_suspect` (46 beyond +300 %/-90 %): mostly real distress; a few ratios every
   source has wrong (BSLI3 2021, TELB4 2011, TIBR5/6 2015).
4. OQ-17 (B3 trade file vs COTAHIST), OQ-19 re-probe on a weekday.
