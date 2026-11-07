# STATUS.md

What is true now. Rewritten in place, never appended; history is in git. Last rewritten 2026-11-07.

## Where the project is

Day one (2026-11-07).
- **Stage A passes its exit criteria** ([evaluation](docs/evaluation/2026-11-07-stage-a-first-daily-run.md)).
- **Stage B (reconnaissance)** has a note for every registered source (31), from two recon passes. Some notes are
  partial (`snd_debentures`; the CVM funds tree has no fixtures yet).
- **Stage C has started**: COTAHIST 1986–2026 is parsed into staging
  ([evaluation](docs/evaluation/2026-11-07-cotahist-full-history.md)).

## What the data layer holds

- **Every ephemeral source found is archived daily**, from the oldest date it still served
  ([coverage](docs/evaluation/2026-11-07-archive-coverage-day-one.md)):
  - B3 instrument and trade files from 2025-06-10;
  - B3 BDI tables from 2026-10-07;
  - five ANBIMA datasets from 2026-10-29;
  - index compositions and the CVM registries from 2026-11-07.
- **Long-history files are archived as published.** COTAHIST yearly 1986– and daily; B3 PR and TS files; Tesouro
  Direto; NEFIN. The TS curve backfill 2001– was running at the end of the session. TS files for 2000 need a holiday
  source before 2001 (ADR-0006).
- **Raw: 1.8 GB on disk.** Large text is compressed at rest (ADR-0009). The host has ~49 GB free.

## Not done, and waiting on whom

- **The owner:**
  - approve registering the Windows scheduled task (`scripts/schedule_daily.ps1`). Until then `fin ingest daily`
    must be run by hand, and **a day not run is lost for the today-only sources**;
  - the disk budget for the PR backfill and the BDI PDF (OQ-20);
  - PLAN §12 (OQ-10 to OQ-16).
- **Engineering:**
  - parsers for the archived ephemeral payloads (ADR-0007);
  - the core `price_daily`: quote factor, currency reforms, deduplicating daily against yearly files;
  - B3 sessions into `calendar_day` (OQ-1);
  - the PETR4 quantity gap (OQ-17).

## Next

1. **Stage C:** CVM cadastro/FCA parsers, the B3 instruments parser (2025-06– files), identity resolution
   (issuer/instrument surrogate keys, ticker and ISIN histories from COTAHIST), `price_daily`, point-in-time universes.
2. **Stage D groundwork:** the IPE index parser (knowledge time of events), and B3 events as tier-U candidates against
   the verified golden table (docs/sources/golden_events.md).
3. **Re-probe B3's 2025-06-10 start** (OQ-19).
