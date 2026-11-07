# cvm_fi_inf_diario — CVM: Informe Diário de Fundos (FI/DOC/INF_DIARIO)

**Tier:** P. **Recon date:** 2026-11-07 (partial; stopped by usage limit). **Fixture:** none yet (nothing downloaded).

Every statement below was measured on the recon date against a real response, unless marked *(from docs)* or
*(not verified)*. Only directory listings, HTTP headers and the zip header lines (via Range) were read.

## 1. Access
- HTTPS file tree `https://dados.cvm.gov.br/dados/` (nginx autoindex behind Cloudflare), no auth; a generic browser UA worked first try. Licence/terms *(not verified)*.
- Headers: `Last-Modified`, nginx-style `ETag` (`"<mtime hex>-<size hex>"`), `Content-Length`, `Accept-Ranges: bytes`, `Cache-Control: public, max-age=14400` (Cloudflare edge, 4 h). `If-None-Match` and `If-Modified-Since` → **304**; `Range` → **206**. Conditional and ranged GETs are usable (same for every file in the CVM tree probed).
- Listing times are Brasília local (UTC-3): listing `07-Nov-2026 00:52` = `03:52 GMT` header.

## 2. Datasets
| dataset_id | granularity | history depth | cadence | publication lag | URL pattern |
|---|---|---|---|---|---|
| monthly | fund/class(/subclass) × day | 2021-01 → current month (2026-11) | rewritten weekly, see §6 | current month present (1.7 MB on 7 Nov) | `FI/DOC/INF_DIARIO/DADOS/inf_diario_fi_YYYYMM.zip` → one member `inf_diario_fi_YYYYMM.csv` (35–58 MB unzipped, 7–12 MB zipped) |
| yearly HIST | same | 2000–2020 (2000/2001 zips ~3.5 KB, 2002–03 2 MB, real volume from 2004) | frozen (LM 2017 / Mar-2022) | — | `FI/DOC/INF_DIARIO/DADOS/HIST/inf_diario_fi_YYYY.zip` (23–93 MB; members not listed) |
| layout | — | — | — | — | `FI/DOC/INF_DIARIO/META/meta_inf_diario_fi.txt` (1891 B, not read) |

## 3. Layout (header line of every monthly file 2021-01…2025-09, read via Range)
- **≤ 2023-11:** `TP_FUNDO;CNPJ_FUNDO;DT_COMPTC;VL_TOTAL;VL_QUOTA;VL_PATRIM_LIQ;CAPTC_DIA;RESG_DIA;NR_COTST`
- **≥ 2023-12:** `TP_FUNDO_CLASSE;CNPJ_FUNDO_CLASSE;ID_SUBCLASSE;DT_COMPTC;VL_TOTAL;VL_QUOTA;VL_PATRIM_LIQ;CAPTC_DIA;RESG_DIA;NR_COTST`
- Types, units, sample rows *(not verified)*; 2025-10…2026-11 and HIST headers not probed.

## 4. Quirks
- **Schema change: 2023-12** is the first file with CVM 175 columns; 2023-11 the last legacy one (measured).
- Separator `;` measured. Encoding (latin-1 expected), decimal separator, date format *(not verified)*.

## 5. Identity fields
- Legacy `CNPJ_FUNDO` → CVM_FUND_CNPJ. New `CNPJ_FUNDO_CLASSE` (class CNPJ) + `ID_SUBCLASSE` → SUBCLASS. Exact semantics *(not verified)*.

## 6. Ephemerality
- Not a snapshot, but files are **rewritten in place**: the trailing ~12 months are regenerated in a Saturday batch (2025-11…2026-09 all LM 31-Oct-2026; 2026-10/11 LM 07-Nov-2026); older months freeze (2021-01 LM 2022-05-01). Rows may be revised for ~1 year → store every ETag as a knowledge-time vintage. Daily rewrite of the current month *(not verified; needs header polling over several days)*.

## 7. Open questions
- meta file; encoding/decimal; sample rows; HIST members/headers; ID_SUBCLASSE fill rule; whether FIEs appear (TP_FUNDO_CLASSE values); build fixture around the golden CVM-175 fund.
