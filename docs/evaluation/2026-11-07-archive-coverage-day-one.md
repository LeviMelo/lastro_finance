# On day one every ephemeral source found is archived for its whole served window, and B3's 17-month files are held whole (2026-11-07)

Regime: uncommitted on top of f1bcf51, data home `data/`, 2026-11-07 08:41–10:45 UTC. Commands: `fin ingest daily` and
per-source runs; `fin ingest b3_instruments --mode backfill`; `fin ingest b3_pesquisapregao --mode backfill
--families TS` (still running when this was written). Counts from the manifest (HTTP 200 rows).

**What is at risk, and what is now held.** The served window is the recon measurement; "held from" is the oldest
reference date in the archive.

| source | served window (recon) | held from | objects | MB as served |
|---|---|---|---|---|
| `b3_instruments` (instruments + trade summary) | since 2025-06-10 | **2025-06-10** (356 + 354 files) | 1,420 | 11,217 |
| `b3_bdi` (settlements, equity open interest, lending, Puma debentures) | 21 business days | 2026-10-07 | 2,843 | 989 |
| `anbima_titulos_publicos`, `_ettj`, `_vna`, `_debentures` | 6 business days | 2026-10-29 | 30 | 2 |
| `anbima_projecoes`, `b3_index_portfolio`, `cvm_cia_cadastro`, `cvm_fi_cadastro` | today only | 2026-11-07 | 50 | 45 |

- The two trade-summary days not held, 2025-12-24 and 2025-12-31, had no B3 session. B3 answers HTTP 400 for them;
  that status is now an absence, not an error.
- **Compression.** The 11.2 GB of B3 files take about 0.9 GB on disk (ADR-0009); all of `raw/` was 1.8 GB.
- **Crash recovery, live.** A backfill stopped by hand after ~15 s (it would have fetched all PR files, an owner
  decision, OQ-20) was sealed `crashed` by the next run, its 3 fetched PR files kept with their manifest rows.

**Still lost before day one, with no free route found.**
- ANBIMA's indicative rates before 2026-10-29: about 5% of days in 2012–2018 in the Internet Archive, not verified
  (OQ-4).
- Index compositions before today: B3's BDI PDF holds them from 2022-03 (OQ-20).
- B3 equity open interest and lending before 2026-10-07.
