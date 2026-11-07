# Stage A passes its exit criteria, and the ephemeral windows were archived whole on day one (2026-11-07)

Regime: first commit of the repository (code as committed with this entry), data home `data/` (fresh), 2026-11-07
08:41–08:47 UTC. Commands: `fin ingest anbima_calendar`, `fin ingest daily`, `fin status`, `fin rebuild --from-raw`;
`uv run pytest` (19 tests).

**Calendar against an independent source (PLAN §10 Stage A: "calendar du matches published examples").**
- The holidays file parsed to 1,264 rows, 0 quarantined (the weekday-name rule held on every row); calendar_day has
  36,159 days (2001-01-01…2099-12-31).
- BCB's CDI publication dates (SGS 12) for 2024-01-02…2025-01-10 equal the calendar's business days exactly.
- BCB's Calculadora do Cidadão factors reproduce to the last of 8 decimals: 1.02621059 (2024-01-02→2024-04-01) and
  1.10875983 (2024-01-02→2025-01-02), as the product over [start, end). Fixed in ADR-0006.

**The first daily run** (`20261107T084150Z-7bcdf0`, status ok, 0 errors) stored 188 raw objects, 95.5 MB:

| source | served window measured in recon | archived on day one |
|---|---|---|
| `b3_bdi` ConsolidatedTradesDerivatives | 21 business days | 21 days × 8 pages of 1,000 rows = 168 objects |
| `anbima_titulos_publicos` | ~6 business days | 6 days × (txt + xls) = 12 objects; 4 older days 404 as expected |
| `cvm_cia_cadastro` | today's snapshot | registry + its metadata |
| `cvm_fi_cadastro` | today's snapshot | `cad_fi.csv`, `cad_fi_hist.zip`, `registro_fundo_classe.zip` + 2 metadata zips |

- The second fetch of the holidays file was answered 304 and recorded as a reconfirmation (ADR-0002).
- So B3's derivative settlements are held from 2026-10-07 and ANBIMA's bond rates from 2026-10-29, the oldest dates
  these sources still served. Earlier days need another route (OPEN_QUESTIONS).

**Rebuild.** `fin rebuild --from-raw` reproduced every staging and core file byte for byte (SHA-256 of each file
compared before and after). Fixed in ADR-0004.

**Not covered.** No parser exists yet for the archived ephemeral payloads (ADR-0007). The daily job is not scheduled yet.
