# STATUS.md

What is true now. Rewritten in place, never appended; history is in git. Last rewritten 2026-11-07.

## Where the project is

Day one (2026-11-07). **Stage A (foundations) passes its exit criteria**
([evaluation](docs/evaluation/2026-11-07-stage-a-first-daily-run.md)):
- the raw store round-trips;
- the calendar's `du` reproduces BCB's published CDI factors;
- `fin rebuild --from-raw` exists and is byte-identical.

**Stage B (reconnaissance) is under way.** The archive of the ephemeral sources started the same day.

## Archiving since 2026-11-07 (ephemeral, ADR-0007)

- **B3 BDI derivatives** (settlements): held from 2026-10-07.
- **ANBIMA bond indicative rates:** held from 2026-10-29.
- **CVM company registry and fund registries:** daily snapshots from 2026-11-07.

The daily job is `fin ingest daily`. It is **not scheduled yet**: `scripts/schedule_daily.ps1` waits for the owner's
approval (RUNBOOK.md).

## Recon coverage

Notes exist for every registered source, but many are partial: a first pass on 2026-11-07 was stopped early to save
the session's usage. Measured so far:
- COTAHIST;
- BCB SGS;
- the ANBIMA calendar and bond rates;
- B3 BDI settlements;
- the CVM company datasets (cadastro, FCA, FRE, IPE index, VLMO);
- the CVM fund file trees.

A second pass (three agents) is filling the gaps:
- B3 instruments, history routes, curves and index portfolios;
- B3 corporate events and the golden events, CVM DFP/ITR;
- Tesouro Transparente, PTAX, Focus, SIDRA, ANBIMA history routes, NEFIN.

## Next

1. **Fold the second recon pass in.** Add every newly found ephemeral source to the daily job, starting with the B3
   reference curves (OQ-5) and the instrument registry (OQ-6). Answer OQ-3 and OQ-4 (long-history routes).
2. **Stage C.** COTAHIST parser (full history), CVM cadastro/FCA, identity resolution, `price_daily`, universes.
3. Parsers for the archived ephemeral payloads, from raw.
