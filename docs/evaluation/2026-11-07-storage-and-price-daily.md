# Storage made lean (deltas, changed rows, compaction) and price_daily built: 7.34 M sessions, 8,464 instruments, 172/173 closes equal an independent source (2026-11-07)

Regime: commits after 0d12636, data home `data/`, 2026-11-07 21:00–22:30 UTC.

| measure | value |
|---|---|
| raw before / after `fin compact-raw` | 3.91 / 3.90 GiB: B3 registry deltas do not pay (date on every line, 81 % of plain zstd) |
| Tesouro daily version, plain zstd / delta | 2.2 MiB / 41 KiB |
| Fundos.NET staging files / size | 17,384 / 129.5 MiB → 11 / 1.3 MiB |
| Tesouro staging (2 snapshots) | 5.7 → 2.9 MB; the second snapshot adds 58 rows, not 178,246 |
| `series_observation` before / after changed-row staging | 585,075 / 585,075 rows (no loss) |
| intraday first archive | 182 symbols, 584,231 5-minute bars (2026-09-14 →), 47.5 MiB downloaded |
| `price_daily` | 7,339,030 rows (lote padrão + fracionário 1986-01-02 → 2026-11-06), 216 MB, built in 33 s |
| instruments / identifier ranges / linked internal codes | 8,464 / 23,412 / 911 |
| duplicate sessions (daily vs yearly file) / disagreeing | 18,613 / 4 |
| closes 2026-11-06 vs Yahoo's last 5-minute bar | 172 of 173 equal; IBOV11 is ×100 on Yahoo |
| currency changeovers, median price ratio | 1986-02 835 (Cruzado plan day), 1989-01 1,033, 1990-03 ~1 (2 stocks), 1993-08 1,002, 1994-07 2,744 |

Disk at the end: raw 4.1 GB, staging 0.8 GB, core 0.22 GB; C: has 49 GB free (95 % used).
