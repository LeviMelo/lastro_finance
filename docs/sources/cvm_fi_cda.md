# cvm_fi_cda — CVM: Composição e Diversificação das Aplicações (FI/DOC/CDA)

**Tier:** P. **Recon date:** 2026-11-07 (partial; stopped by usage limit). **Fixture:** none yet.

Every statement below was measured on the recon date against a real response, unless marked *(from docs)* or
*(not verified)*. Only listings and HTTP headers were read.

## 1. Access
- Same CVM tree and header behaviour as `cvm_fi_inf_diario.md` §1.

## 2. Datasets
| dataset_id | granularity | history depth | cadence | publication lag | URL pattern |
|---|---|---|---|---|---|
| monthly | fund × asset × month | 2023-01 → 2026-10 | trailing months rewritten weekly | 2026-10 present on 07-Nov but 2 MB (full months ~25 MB); 2026-08/09 15 MB → a month fills over ~3+ months | `FI/DOC/CDA/DADOS/cda_fi_YYYYMM.zip` (19–26 MB) |
| yearly HIST | same | 2005–2022 | frozen | — | `FI/DOC/CDA/DADOS/HIST/cda_fi_YYYY.zip` (27–140 MB) |
| layout | — | — | — | — | `FI/DOC/CDA/META/meta_cda_fi_txt.zip` (10 KB, not read) |

## 3–5. Layout, identity
- Member files (BLC_1..8, CONFID, PL, fiim), columns and asset identifiers *(not verified)*.

## 4. Quirks
- Recent months grow as late filings arrive; store per-ETag vintages, knowledge time = first seen.
- 2024-02…2025-01 were all rewritten on 18-Feb-2026 (bulk reprocessing of frozen months happens).

## 6. Ephemerality
- Not ephemeral; revised in place.

## 7. Open questions
- Members/columns; exact lag; confidentiality window.
