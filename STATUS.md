# STATUS.md

What is true now. Rewritten in place, never appended; history is in git. Last rewritten 2026-11-07.

## Where the project is

Day one (2026-11-07).
- **Scope set by the owner** (ADR-0011): the ledger starts in 2026; the holdings are stocks, FIIs, ETFs and Tesouro
  Direto; economic context data is a domain of its own.
- **Collection terms** (ADR-0012): automating what the owner could fetch by hand for the owner's own portfolio is the personal
  use the sources' general terms allow. Collection stays polite and is never redistributed.
- **Stage A passes its exit criteria.** **Stage B** has a note for every registered source (52). **Stage C**:
  - core `price_daily` (spot and odd lot, 1986–2026, 7.34 M sessions) with instrument identity: 8,464
    instruments, ISIN and time-ranged tickers, 911 pre-1995 codes linked (ADR-0015);
  - core `series_observation`: 1,174 macro and market series, 585,075 values with units (ADR-0013);
  - staging: Tesouro Direto 2004–, FII distributions, CVM statements 2010– (66.8 M lines), intraday 5-minute bars
    (archived from 2026-11-07).
- **Storage is lean by rule** (ADR-0014): re-sent files as deltas, CVM zips as member deltas, staging keeps changed
  rows, small files compacted. C: has 49 GB free: the binding limit.
- **Data gaps are mapped and ranked** ([gap matrix](docs/evaluation/2026-11-07-data-gap-matrix.md)). Everything
  priority 1 needs has a free route.

## What the data layer holds (raw 4.1 GB, staging 0.8 GB, core 0.2 GB)

- **Holdings data (priority 1):**
  - COTAHIST prices 1986–;
  - FII distributions 2016– (Fundos.NET backfill running: about half of 36,584 notices at 22:30 UTC);
  - Tesouro Direto 2004–; VNA 2000–; CDI and Selic 1986–; IPCA 1979–;
  - Yahoo events for 848 tickers (U), and the CVM filings index 2003–, which proves them.
- **Company data:**
  - CVM statements (DFP 2010–, ITR 2011–), FCA, FRE and IPE, kept as versions from now on;
  - B3 instrument files 2025-06–.
- **Context data (priority 2)** ([backfill](docs/evaluation/2026-11-07-context-catalogue-backfill.md)), from the
  catalogue `src/fin/reference/context_series.toml`:
  - Brazilian macro: 60 SGS series, 11 SIDRA tables, Ipeadata, Copom since 1996, Focus since 2000;
  - B3 index levels (Ibovespa 1968–); B3 curves 2001–; futures 2018– (mirror);
  - global rates (Treasury, Fed, ECB, BIS), VIX, oil, commodities (Pink Sheet 1960–, IMF, CEPEA), OECD leading
    indicators, CFTC positioning.
- **Ephemeral sources are archived daily**: ANBIMA (6 datasets including IMA), B3 BDI tables (including investor
  flows), index compositions, CVM registries, SND terms, and Yahoo 5-minute bars (U). The 2026-11-07 run was started by
  hand (0 errors).

## Not done, and waiting on whom

- **The owner:**
  - approve registering the Windows scheduled task (`scripts/schedule_daily.ps1`). Until then `fin ingest daily`
    runs by hand, and **a day not run is lost for the today-only sources**;
  - free FRED and Tiingo tokens (OQ-23);
  - paid sources (OQ-10); PLAN §12 OQ-11 and OQ-14 to OQ-16.
- **Engineering:**
  - parsers for the other archived payloads (ADR-0007): CFTC, Focus, Copom, CEPEA, ANP, ANBIMA IMA;
    then the B3 snapshots, CVM FCA/FRE/IPE and the ANBIMA files;
  - fundamentals: `fundamental_fact` from `statement_line` (scale applied, accounts mapped per sector);
  - the mirror-vs-ANBIMA overlap check; calendar 1986–2000 (OQ-22);
  - universes (point in time), identity links across ISIN changes (needs events), ESPECI table for asset classes.

## Next

1. **Corporate events** (PLAN §4.3.3): B3 events + Yahoo candidates proven against CVM IPE; they link ISIN changes
   and give adjusted series (derived, never stored as truth).
2. **Holdings tables in core:** FII distributions with their delivery minute; `tesouro_price_daily`; universes.
3. **Fundamentals** from `statement_line`: scale applied, accounts mapped per sector (banks differ from industrials).
4. **Remaining context parsers:** Focus expectations, Copom, CFTC, CEPEA, ANP, ANBIMA IMA.
