# EVALUATION.md

The index of this project's measurements. Each one is a file under `docs/evaluation/`; read the index, then the
entries you need. What counts as ground truth: [`docs/evaluation/methods.md`](docs/evaluation/methods.md).

**Nothing is declared working on a plausible-looking output.** Open the table, and check it against an independent
figure: the source's own totals, a second source, a documented event.

A new measurement is a file `docs/evaluation/YYYY-MM-DD-<slug>.md` plus a row here, in the same commit as the work it
justifies. It names the command or script, the regime (commit, data home, date), what was counted and why that is what
matters, and the result against the independent figure.

| date | entry | what was measured |
|---|---|---|
| 2026-11-07 | [Stage A and the first daily run](docs/evaluation/2026-11-07-stage-a-first-daily-run.md) | calendar against BCB's CDI dates and factors; first archive of the ephemeral windows; rebuild from raw byte-identical |
| 2026-11-07 | [COTAHIST full history](docs/evaluation/2026-11-07-cotahist-full-history.md) | 1986–2026 loaded, quarantine by rule, sessions vs calendar, field check against B3 TradeInformation |
| 2026-11-07 | [Archive coverage on day one](docs/evaluation/2026-11-07-archive-coverage-day-one.md) | every ephemeral source against its served window; B3 17-month backfill; compression; live crash recovery |
| 2026-11-07 | [Data gap matrix](docs/evaluation/2026-11-07-data-gap-matrix.md) | 19 gaps against PLAN's scope: free, mirror, unofficial, scraping and paid routes, verified; what each closes |
| 2026-11-07 | [Context catalogue backfill](docs/evaluation/2026-11-07-context-catalogue-backfill.md) | 21 context sources archived from their first date; Focus %20 and SGS window fixes |
| 2026-11-07 | [Series core, first build](docs/evaluation/2026-11-07-series-core-first-build.md) | SGS, Ipeadata, SIDRA → `series_observation`: 1,017 series, 0 quarantined, IPCA SGS = SIDRA, reparse byte-identical |
| 2026-11-07 | [Storage and price_daily](docs/evaluation/2026-11-07-storage-and-price-daily.md) | raw deltas, changed-row staging, compaction measured; price_daily 7.34 M sessions, identity, 172/173 closes equal Yahoo |
| 2026-11-07 | [Corporate events](docs/evaluation/2026-11-07-corporate-events.md) | 35,056 events; golden stock and cash cases exact; split adjustment equals Yahoo on 7 large caps; total-return differences explained |
| 2026-11-07 | [Fundamentals mapping](docs/evaluation/2026-11-07-fundamentals-mapping.md) | 15 metrics by account name across industrial and bank templates; 441-458 companies per metric (DFP 2024) |
| 2026-11-08 | [Golden portfolio](docs/evaluation/2026-11-08-golden-portfolio.md) | §13.1 portfolio total +37.38 % vs +37.2 %, price +28.69 % vs +28.5 %; B3 cash names with "/" fixed (572 events) |
| 2026-11-08 | [Exit criteria C, E, G, H](docs/evaluation/2026-11-08-exit-criteria.md) | calendar vs sessions exact; Selic and CDI compounding 323/323 months; LTN PU 93.06 % (Tesouro irregularities); balance identity 24,813/24,819; restatements point-in-time 21/21 |
