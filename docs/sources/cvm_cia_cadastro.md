# cvm_cia_cadastro - CVM: cadastro de companhias abertas

**Tier:** P. **Recon date:** 2026-11-07. **Fixture:** `tests/fixtures/cvm_cia_cadastro/cad_cia_aberta.csv`. Fixture lines are byte-exact (cp1252): the header plus the rows of Itau 60.872.504/0001-23, Petrobras 33.000.167/0001-01, Natura &Co 32.785.497/0001-97 (registration cancelled 2025-07-01, by incorporation) and BRF 01.838.723/0001-27 (BRFS3 trading ended 2025-09-22).

Every statement was measured on 2026-11-07 against a real response unless marked *(not verified)*. Recon was cut short by a usage-limit stop; gaps are listed under Open questions.

## 1. Access
- HTTPS file tree https://dados.cvm.gov.br/dados/CIA_ABERTA/ (nginx autoindex behind Cloudflare). No auth. A generic UA worked; no blocking was seen.
- Headers: `Last-Modified`, `ETag` (nginx style, mtime-hex/size-hex) and `Content-Length`. `If-None-Match` and `If-Modified-Since` both return **304**. `Accept-Ranges: bytes` gives 206, so single zip members can be read without the whole zip (central directory first, then member ranges). Cloudflare `Cache-Control: max-age=14400`.
- The autoindex shows times in BRT (UTC-3), and Last-Modified is in GMT.
- CKAN API (`/api/3/action/package_list`, `package_show`): *(not verified)*.
- Regeneration seen: the current year and the four years before it were all rewritten on 2026-11-01 (a Sunday, about 07:00-08:50 BRT), so the cycle looks weekly *(cadence inferred from one listing)*. Older years are frozen, e.g. 2021 last written 2025-12-28 and 2020 on 2024-12-29. So a year is rewritten for about 5 years after it ends.
- This file is regenerated **daily** (Last-Modified 2026-11-07 04:09 GMT). Size 1,494,679 B.

## 2. Datasets
| dataset_id | granularity | history | cadence | URL |
|---|---|---|---|---|
| cad_cia_aberta | one row per (CNPJ, CVM registration, TP_MERC) | registrations since 1923, cancellations since 1984 | daily snapshot | CAD/DADOS/cad_cia_aberta.csv; CAD/META/meta_cad_cia_aberta.txt |

## 3. Layout
47 columns: CNPJ_CIA;DENOM_SOCIAL;DENOM_COMERC;DT_REG;DT_CONST;DT_CANCEL;MOTIVO_CANCEL;SIT;DT_INI_SIT;CD_CVM;SETOR_ATIV;TP_MERC;CATEG_REG;DT_INI_CATEG;SIT_EMISSOR;DT_INI_SIT_EMISSOR;CONTROLE_ACIONARIO;(address);TP_RESP;RESP;(DRI contact);CNPJ_AUDITOR;AUDITOR.
- On the recon date the file had 2,679 rows, 2,532 distinct CNPJ and 2,568 distinct CD_CVM.
- SIT: CANCELADA 1916, ATIVO 755, SUSPENSO(A) - DECISAO ADM 8.
- TP_MERC: BOLSA, BALCAO ORGANIZADO, BALCAO NAO ORGANIZADO, or blank.

## 4. Quirks
- Encoding is latin-1/cp1252 (not valid UTF-8, no C1 bytes), no BOM, ';' separator, CRLF, ISO dates.
- **Duplicate rows by TP_MERC:** a company on both markets appears twice, identical except TP_MERC. Petrobras (9512) has a BOLSA row and a BALCAO ORGANIZADO row.
- **One CNPJ can have several CVM codes:** each re-registration gets a new one. Itau has code 1279 (cancelled 1998-04-08) and code 19348 (active since 2002-12-30). Bradesco Leasing has 3 codes.
- Cancelled rows can keep TP_MERC and CATEG_REG, e.g. Natura &Co 24783, cancelled 2025-07-01 ("ELISAO POR INCORPORACAO").
- The file contains contact data of named DRIs.

## 5. Identity fields
- CNPJ_CIA maps to CNPJ, the issuer anchor.
- CD_CVM maps to CVM_CODE. It is time-ranged by DT_REG to DT_CANCEL and is not 1:1 with CNPJ.
- The names are current names only.

## 6. Ephemerality
**Current snapshot only.** It has no name history and keeps only the current SIT, CATEG_REG and SIT_EMISSOR with their start dates; earlier values are overwritten. Archive it daily from day one. Name history must come from FCA geral (Nome_Empresarial_Anterior).

## 7. Open questions
- Whether CVM codes are ever reused by another company *(not verified)*.
- Whether old snapshots are archived anywhere *(not verified)*.
