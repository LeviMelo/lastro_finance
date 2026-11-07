# cvm_fii — CVM: informes FII (mensal / trimestral / anual) and FIAGRO

**Tier:** P. **Recon date:** 2026-11-07 (partial; stopped by usage limit). **Fixture:** none yet.

Every statement below was measured on the recon date against a real response, unless marked *(from docs)* or
*(not verified)*. Only listings and HTTP headers were read.

## 1. Access
- Same CVM tree and header behaviour as `cvm_fi_inf_diario.md` §1.

## 2. Datasets
| dataset_id | granularity | history depth | cadence | publication lag | URL pattern |
|---|---|---|---|---|---|
| FII inf_mensal | fund × month | 2016–2026 (yearly zips 57 KB–1.3 MB) | 2022–2026 rewritten weekly (LM 31-Oct-2026) | *(not verified)* | `FII/DOC/INF_MENSAL/DADOS/inf_mensal_fii_YYYY.zip`; `META/meta_inf_mensal_fii.zip` |
| FII inf_trimestral | fund × quarter | 2016–2026 | same | — | `FII/DOC/INF_TRIMESTRAL/DADOS/inf_trimestral_fii_YYYY.zip` |
| FII inf_anual | fund × year | 2016–2026 | same | — | `FII/DOC/INF_ANUAL/DADOS/inf_anual_fii_YYYY.zip` |
| FII DFIN | — | — | — | — | `FII/DOC/DFIN/` (not listed) |
| FIAGRO inf_mensal | fund × month | 2025-05 → 2026-09 (monthly zips 2.8 → 73 KB) | monthly | ~1 month | `FIAGRO/DOC/INF_MENSAL/DADOS/inf_mensal_fiagro_YYYYMM.zip` |

## 3–5
- Members and columns (NAV, cotas, rendimentos, DY) *(not verified)*.

## 7. Open questions
- All layouts; where FIAGRO before 2025-05 lives (inside FII files?).
