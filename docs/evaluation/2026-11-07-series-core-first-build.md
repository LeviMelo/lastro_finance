# SGS, Ipeadata and SIDRA parse into core `series_observation`: 1,017 series, 204,136 values, 0 quarantined (2026-11-07)

**Setup.**
- Regime: `ingest/series.py` (ADR-0013) on the archive of 2026-11-07.
- Metadata was fetched by run 20261107T201928Z-97e32e: 67 SGS SOAP answers and 16 Ipeadata ones, 0 errors.
- Command: `fin reparse bcb_sgs ipeadata ibge_sidra`.

| measure | value |
|---|---|
| staging observations | 209,620 in; 8 quarantined, later 0 once SGS JSON null was read as missing (M2/M3 2001-08..11) |
| core rows / series | 204,136 / 1,017 (M 108,465; D 95,009; Q 487; M3 175) |
| core rows without a definition or off-grid | 0 |
| objects that are not data | 2 SGS payloads: BCB's HTML "Requisição inválida!" page with HTTP 200 (sgs_12 2006–2016, retried OK; sgs_25 2021–2026, after the series ended) |
| idempotency | a second reparse gives byte-identical staging and core (226 files) |

**Checks against the sources.**
- IPCA Sep-2026: SGS 433 = SIDRA 1737 v63 = 0.82.
- IGP-M index Oct-2026 = 1243.905 (Ipeadata).
- Unemployment (rolling quarter Jul–Sep 2026) = 5.2.

**Added the same day: Tesouro VNA** (`fin reparse tesouro_vna`):
- 3 series: NTN-B 316 months, two NTN-C groups; 239 zero cells kept as missing ("matured").
- NTN-B against IBGE's IPCA index: trunc(1000 × IPCA(m−1)/IPCA(Jun-2000), 6 dp) is exact on 315 of 316 months.
  The exception is 2014-02 (source note `tesouro_vna`).

**Found.**
- SGS 226 (TR) has several periods per start date: `data` 01/05/1991 ends on both 30/05 and 31/05. A period is
  therefore its start and its stated end.
- With that key, no series shows a revision inside one day of fetches.
- SGS SOAP gives `R$ (milhões)` for 20539, where CKAN says "unidades monetárias correntes". The SOAP text is used
  (ADR-0013).
- Ipeadata's unit is `-` for index series (IGP-M, EMBI+). It is kept as written, and the name states the base
  ("ago. 1994 = 100").
