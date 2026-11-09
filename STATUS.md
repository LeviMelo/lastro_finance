# STATUS.md

What is true now. Rewritten in place, never appended; history is in git. Last rewritten 2026-11-09.

## Where the project is

Day three (2026-11-09). The data layer (stages A–H) is built and measured; the ledger and tax engine (I) run on a
transactions CSV (empty until the owner invests); the dossier (L) and portfolio analytics (K) read the ledger or a
portfolio file.
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
  - raw 13 GB, staging 7.1 GB, core 0.25 GB; C: has 35 GB free;
  - large sources are streamed: only the used part of each download is kept, with a fingerprint of the whole
    (Price Report tar+zstd, ADR-0031; daily bulletin PDF, ADR-0034);
  - DuckDB connections cap temp files at 4 GB (a view once spilled 38 GB).

## What the data layer holds

- **Exchange-traded:**
  - COTAHIST prices 1986– (8,469 instruments, identity through ISIN and ticker changes);
  - corporate events 53,003 (ADR-0016, ADR-0035), adjusted prices on read. Every stock event is decided; a ratio
    comes from B3's lists, then the filing's own text (`cvm_ipe_docs`), then B3's EG (ex-grupamento) marker in
    COTAHIST, then the price move (TELB4 2011 10,000:1 from the filing, Yahoo said 1:10; TIBR5/6 2015 1:100 from the
    EG marker; BTTL3 2015 25:1);
  - B3 Price Report 2018– (2,199 days, 64.5 M rows, 3.2 GB as tar+zstd, ADR-0031): settlements, open interest,
    options and the fixed-income ETFs COTAHIST omits (36 of them priced and verified against NAV, IMAB11 on 1,857 days);
  - B3's listed funds (daily);
  - daily bulletin PDF 2022-03– (ADR-0034), backfill running: index compositions of 31 indices per session, and
    stock lending (registered loans; open balances by market, the short-interest series);
  - index membership per month (ADR-0036): B3's portfolios from 2022-03, before that the holdings of the ETF
    measured to track each index (Ibovespa, SMLL, IBrX-50/100, ISE, ICO2, IGCT, IMAT from 2018).
- **Companies:**
  - issuers linked to their shares through B3 roots, FCA codes, the ISIN issuer code, B3's ISIN registry and name
    history: 1,177 of 1,204 share and unit lines trading since 2010; unlinked volume ~0 from 2013 (ADR-0018);
  - CVM DFP/ITR 2010– plus superseded versions from RAD (backfill running, ~350/h, CVM's server-bound: its
    'service busy' pages are retried, never read as absent);
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
- **Ledger and tax** (ADR-0033): `fin ledger` and `fin tax` run on a transactions CSV:
  - average cost, day trade, corporate events from core, double-entry postings;
  - monthly IR per pool with the R$ 20,000 exemption, carried losses and IRRF, DARF 6015 due dates;
  - JCP 17.5 % and the dividend rule of Lei 15.270 from 2026; Tesouro IOF and IR;
  - rules dated in `tax/rules.toml` with legal references (docs/sources/tax_rules.md).
- **Dossier** (ADR-0026): holdings (stocks, FIIs, ETFs incl. fixed-income, Tesouro Direto), valuation,
  performance, risk with ETF look-through, events, fundamentals, quality findings.

## Not done

- **Blocked by the harness:** the Windows scheduled task and any in-session loop are refused as persistence.
  `fin ingest daily` runs by hand; a day not run is lost for the today-only sources.
- **Stage I gaps** (ADR-0033): come-cotas, crypto, offshore, options, futures and shorts; reconciliation with B3's investor-portal export.
- **Owner decisions:**
  - B3 HistoricoRF aggregate files (a form with a reCAPTCHA field);
  - ANBIMA Data (login);
  - paid sources (OQ-10).
- **Measured as closed:**
  - ANBIMA daily ETTJ, bond rates before 2020, VNA and projections history;
  - B3 futures settlements before 2018 (OQ-3: COTAHIST has 26 forward rows ever; curves from TaxaSwap 2000–);
  - CVM fundamentals before 2010.

## Next (engineering)

1. RAD and bulletin backfills to completion; then the H check, core events, catalog, panel and quality rebuilt.
2. Panel month-returns flagged `ret_suspect` (67 beyond +300 %/-90 %): mostly real distress; moves with no event
   and no filing found (TIBR5/6 2015, BTTL3 2015, PTPA3 2016) stay flagged.
3. OQ-17 (B3 trade file vs COTAHIST), OQ-19 re-probe on a weekday.
