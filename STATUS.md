# STATUS.md

What is true now. Rewritten in place, never appended; history is in git. Last rewritten 2026-11-07.

## Where the project is

Day one (2026-11-07).
- **Stage A passes its exit criteria** ([evaluation](docs/evaluation/2026-11-07-stage-a-first-daily-run.md)).
- **Stage B (reconnaissance)** has a note for every registered source (36), from three recon passes.
- **Data gaps are mapped and ranked** ([gap matrix](docs/evaluation/2026-11-07-data-gap-matrix.md), ADR-0010).
  Of 19 gaps against PLAN's scope:
  - 11 are closed by a free verified route; 4 of these go through a mirror or an unofficial source;
  - 5 are partly closed;
  - 3 have no free route: ANBIMA CRI/CRA, ETTJ, IMA and projection history; B3 futures before 2018; fundamentals
    before 2010.
- **Stage C has started**: COTAHIST 1986–2026 is parsed into staging
  ([evaluation](docs/evaluation/2026-11-07-cotahist-full-history.md)).

## What the data layer holds

- **Every ephemeral source found is archived daily**, from the oldest date it still served
  ([coverage](docs/evaluation/2026-11-07-archive-coverage-day-one.md)). SND's debenture terms (daily) and agenda
  (weekly) joined them.
- **Long-history files are archived as published:**
  - COTAHIST yearly 1986– and daily;
  - B3 TS curves 2001– (6,402 files, 0 errors); TS files for 2000 need a calendar before 2001 (OQ-22);
  - Tesouro Direto; NEFIN.
- **Routes that close gaps, archived 2026-11-07:**
  - ANBIMA bond rates 2020– and B3 futures 2018–, through the `pyield_data` mirror;
  - IGP-M and IGP-DI index numbers (Ipeadata); Tesouro's VNA tables;
  - BCB SGS 11/12/432/1178/4389 from 1986.
- **Backfills still running at the end of the session:**
  - SND trade statistics 1993–;
  - Yahoo charts for 896 tickers;
  - Fundos.NET FII distribution notices 2016–, about 10 h.

## Not done, and waiting on whom

- **The owner:**
  - approve registering the Windows scheduled task (`scripts/schedule_daily.ps1`). Until then `fin ingest daily`
    must be run by hand, and **a day not run is lost for the today-only sources**;
  - disk for the PR backfill and the BDI PDF (OQ-20): the PDF is the only route found for index compositions and
    equity lending in 2022–2026;
  - paid sources (OQ-10): none sells the open gaps to an individual at a published price;
  - free API tokens for Tiingo and FRED (OQ-23);
  - PLAN §12 (OQ-11 to OQ-16), including whether crypto and offshore holdings exist (OQ-13).
- **Engineering:**
  - parsers for the archived payloads (ADR-0007, ADR-0010);
  - the mirror-vs-ANBIMA overlap check as a `dq_finding`;
  - calendar 1986–2000 from SGS (OQ-22);
  - the core `price_daily`; B3 sessions into `calendar_day` (OQ-1); the PETR4 quantity gap (OQ-17).

## Next

1. **Stage C:** CVM cadastro/FCA parsers, the B3 instruments parser, identity resolution, `price_daily`,
   point-in-time universes; the CVM CDA parser, which also gives index-ETF holdings, i.e. index constituents
   2018-06– (gap 10).
2. **Stage D groundwork:** the IPE index parser; Yahoo and B3 events as candidates against IPE (OQ-18).
3. **Re-probe:** B3's 2025-06-10 start (OQ-19); Mercado Bitcoin's API (Cloudflare 521 on 2026-11-07).
