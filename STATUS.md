# STATUS.md

What is true now. Rewritten in place, never appended; history is in git. Last rewritten 2026-11-07.

## Where the project is

Day one (2026-11-07).
- **Scope set by the owner** (ADR-0011): the ledger starts in 2026; the holdings are stocks, FIIs, ETFs and Tesouro
  Direto; economic context data is a domain of its own.
- **Collection terms** (ADR-0012): automating what the owner could fetch by hand for the owner's own portfolio is the personal
  use the sources' general terms allow. Collection stays polite and is never redistributed.
- **Stage A passes its exit criteria.** **Stage B** has a note for every registered source (51). **Stage C** has
  started: COTAHIST 1986–2026 is parsed to staging; SGS, Ipeadata and SIDRA are parsed into core
  `series_observation` (1,017 series, 204,136 values, every row with its unit; ADR-0013).
- **Data gaps are mapped and ranked** ([gap matrix](docs/evaluation/2026-11-07-data-gap-matrix.md)). Everything
  priority 1 needs has a free route.

## What the data layer holds (raw: 4.0 GB)

- **Holdings data (priority 1):**
  - COTAHIST prices 1986–;
  - FII distributions 2016– (Fundos.NET backfill running, ~25 % done at 18:30 UTC);
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
  flows), index compositions, CVM registries, SND terms. The 2026-11-07 run was started by hand (0 errors).

## Not done, and waiting on whom

- **The owner:**
  - approve registering the Windows scheduled task (`scripts/schedule_daily.ps1`). Until then `fin ingest daily`
    runs by hand, and **a day not run is lost for the today-only sources**;
  - free FRED and Tiingo tokens (OQ-23);
  - paid sources (OQ-10); PLAN §12 OQ-11 and OQ-14 to OQ-16.
- **Engineering:**
  - parsers for the other archived payloads (ADR-0007): the global context sources, Focus, Copom, CEPEA, ANP into
    `series_observation`; units and scales checked per entry;
  - the mirror-vs-ANBIMA overlap check; calendar 1986–2000 (OQ-22);
  - `price_daily`, identity resolution, universes.

## Next

1. **Stage C:** parsers and core tables in the order of priority 1:
   - `price_daily` from COTAHIST;
   - events: B3 + Yahoo candidates proven against IPE;
   - FII distributions; Tesouro Direto prices; CDI, IPCA and VNA;
   - identity resolution from COTAHIST, FCA and the CVM registry.
2. **Context parsers** for the remaining catalogue sources into `series_observation` (SGS, Ipeadata, SIDRA done).
3. **Fundamentals** from DFP/ITR, mapped per sector layout (banks differ from industrials).
