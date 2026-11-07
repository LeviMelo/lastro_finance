# COTAHIST 1986–2026 loads whole, 1,241 rows quarantined, and agrees with B3's other daily file except on PETR4's quantity (2026-11-07)

Regime: uncommitted on top of f1bcf51, data home `data/`, 2026-11-07 08:54–09:12 UTC. Commands: `fin ingest b3_cotahist`
(10 daily files), `--mode backfill --years 1986-2024`, `--years 2025`, `--years 2026`, then `fin rebuild --from-raw`.

**What was loaded.** 41 yearly files plus 10 daily files: 884 MB of raw for the whole archive, of which the COTAHIST
zips are most. After the rebuild, `quote` took 24,991,390 rows in, 24,990,149 out and 1,241 quarantined, with 0
objects in error. Daily files overlap the 2026 yearly file; the core layer will deduplicate them.

**Integrity against the files' own counts.**
- Every trailer count matched one of the two conventions: records + 2 (1986, as the PDF says) or records (2025–2026).
  Which year the convention changed was not isolated *(not verified)*.
- One 2026 line was 246 bytes, because of UTF-8 "Â". It was repaired and flagged (ADR-0008).

**Quarantine (1,241 rows), each a real anomaly of the source, kept whole.**

| rule | rows | where |
|---|---|---|
| open or close outside [low, high] | 1,237 | 633 in 2005, 280 in 2020, the rest scattered; spot, odd lot, termo and options alike |
| low > high | 2 | — |
| FATCOT = 0 | 4 | 2007 |

The first load also quarantined `FATCOT` 100000 (2005) and 1000000 (2016–2017), 77 rows. These are powers of ten, so
the rule now accepts 1…10⁶ (contract v2).

**Sessions against the calendar.** From 2001 to 2025, B3 traded on no ANBIMA holiday or weekend. It did not trade on
287 ANBIMA business days: São Paulo holidays, 24/12, 31/12, 20/11 before 2024, the 2014 World Cup opening (OQ-1).

**Independent check, field by field.** Against B3's TradeInformationConsolidated for 2026-11-06 (a different B3 product):
- BOVA11 and HGLG11 agree on low, high, last, trades, quantity and volume.
- PETR4 agrees on prices and its 70,037 trades, but has 400,000 more shares (R$ 18.1 M) there (OQ-17).

**Not covered.** No check yet against a third party (Yahoo or a broker statement) or of option strikes; the core
`price_daily` (quote-factor normalisation, currency reforms) does not exist yet.
