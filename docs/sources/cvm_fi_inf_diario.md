# cvm_fi_inf_diario — CVM: Informe Diário de Fundos (FI/DOC/INF_DIARIO)

**Tier:** P. **Recon:** 2026-11-07. **Parser:** `src/fin/ingest/cvm_funds.py` (`CvmFiInfDiario`). **Fixtures:** `tests/fixtures/cvm_fi_inf_diario/`.

Every statement was measured on 2026-11-07 against real files unless marked *(from docs)*.

## 1. Access
- HTTPS tree `https://dados.cvm.gov.br/dados/` (nginx autoindex behind Cloudflare), no auth; the generic `lastro-fin` UA worked at 1 request/s. Licence/terms *(not verified)*.
- Headers: `Last-Modified`, nginx-style `ETag` (`"<mtime hex>-<size hex>"`), `Content-Length`, `Content-Type: application/zip`, `Accept-Ranges`, `Cache-Control: public, max-age=14400`. `If-None-Match`/`If-Modified-Since` give 304; `Range` gives 206 (used to read zip directories without downloading). A missing file is a 404 with `text/html`.
- Listing times are Brasília (UTC-3).

## 2. Datasets
| dataset_id (staging) | granularity | history | URL |
|---|---|---|---|
| daily, partition `month=YYYYMM` | fund/class(/subclass) x day | 2000 to 2026-11 | monthly zips 2021-01..2026-11 (71, 749 MB, 8-12 MB each) `FI/DOC/INF_DIARIO/DADOS/inf_diario_fi_YYYYMM.zip`; yearly HIST 2000-2020 (21, 934 MB; 2000/2001 3.5 KB, 2004 24 MB, 2020 93 MB) `.../DADOS/HIST/inf_diario_fi_YYYY.zip` whose members are **monthly** csv (`inf_diario_fi_202001.csv`...; 2000 and 2001 have one `inf_diario_fi_2001.csv` each, partition `year=2001`) |
- Meta `META/meta_inf_diario_fi.txt` (1,891 B, latin-1): VL_QUOTA numeric(27,12); VL_TOTAL, VL_PATRIM_LIQ, CAPTC_DIA, RESG_DIA numeric(17,2); NR_COTST int; ID_SUBCLASSE varchar(15).
- Rows: 538,519 in 2026-09 (54.5 MB csv), 478,449 in 2025-11, 389,625 in 2021-01, 123,400 in 2005-01. 4.33 M rows parsed from 2005-01..12, 2021-01, 2022-02, 2023-11/12, 2024-12, 2025-11, 2026-09 with 0 quarantined.

## 3. Layout (checked in code; three header eras of one table)
- CVM 175 (2023-12 on): `TP_FUNDO_CLASSE;CNPJ_FUNDO_CLASSE;ID_SUBCLASSE;DT_COMPTC;VL_TOTAL;VL_QUOTA;VL_PATRIM_LIQ;CAPTC_DIA;RESG_DIA;NR_COTST`.
- 2021-01..2023-11: the same without `ID_SUBCLASSE`, names `TP_FUNDO`, `CNPJ_FUNDO` (value `FI`).
- HIST 2002-2020: no `TP_FUNDO` either (`CNPJ_FUNDO;DT_COMPTC;...`); the 2001 file has it (`FIC-FITVM`, `FITVM`).
- `;`, CRLF, ASCII in every month read, ISO dates, `.` decimal, quota with 12 decimals. Empty `VL_TOTAL` and `NR_COTST` occur (2001).
- 2026-09 `TP_FUNDO_CLASSE`: `CLASSES - FIF` 538,103 rows, `CLASSE FIF/FAPI` 273, `FI` 143. 20,206 rows carry an `ID_SUBCLASSE` (e.g. `RBMFN1747320951`, fund 00.888.897/0001-31): the key is (CNPJ, subclass, date), not (CNPJ, date).
- Negative values are real: 32 funds have a negative quota in 2026-09 (e.g. 09.613.232/0001-90, quota -0.97, net assets -17.5 M): kept, no rule.
- Spot: 07.593.972/0001-86 on 2026-09-30: quota 8.497325, net assets 284,132,679,911.60 (the largest of the month), subscriptions 1,072,831,957.54, holders 250; the staged parquet equals the line.

## 4. Footprint (repo zstd-9 raw store and parquet staging, measured)
- One month (2025-11, 478 k rows): csv 48 MB, raw 11.7 MB, staging 9.7 MB. HIST 2005 (12 members, 124 MB csv): raw 34.4 MB, staging 29.4 MB. Projection: monthly 2021-01..2026-11 raw ~0.85 GB + staging ~0.70 GB; HIST raw ~1.07 GB + staging ~0.92 GB. Weekly rewrites add deltas (a restated row: 1 of 538,519 landed in the dedup test).

## 5. Ephemerality
- Rewritten in place: the trailing ~12 months are regenerated in a Saturday batch (2025-11..2026-09 LM 31-Oct-2026; 2026-10/11 LM 07-Nov-2026), older months freeze (2021-01 LM 2022-05-01). Rows may be revised for ~1 year: every ETag is a knowledge-time vintage. Plan: current and previous month daily (304 when unchanged), months 2-13 weekly, older monthly; never-seen old months and HIST only by backfill.

## 6. Open questions
- Publication lag of the current month; daily rewrite of the current month (needs several days of polling); which `TP_FUNDO_CLASSE` values are FIE/FIDC.
