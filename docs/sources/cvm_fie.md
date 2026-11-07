# cvm_fie — CVM: FIE (previdência) trees, plus the other FI/DOC datasets

**Tier:** P. **Recon date:** 2026-11-07 (partial; stopped by usage limit). **Fixture:** none.

Every statement below was measured on the recon date (directory listings only) unless marked *(not verified)*.

## 1. Access
- Same CVM tree and header behaviour as `cvm_fi_inf_diario.md` §1.

## 2. Datasets
| dataset_id | history depth | URL pattern |
|---|---|---|
| FIE medidas mensais | 2017-01 → 2026-09, monthly csv 97–771 KB | `FIE/MEDIDAS/DADOS/medidas_mes_fie_YYYYMM.csv`; `META/meta_medidas_mes_fie.txt` |
| FIE balancete | 2024-01 → 2026-09 (+ HIST/) | `FIE/DOC/BALANCETE/DADOS/balancete_fie_YYYYMM.zip` |
| FIE balanço | not listed | `FIE/DOC/BALANCO/` |
| FIE cadastro | **directory empty** | `FIE/CAD/DADOS/` |
| FI lâmina | HIST 2014-01…2018-12; DADOS 2019-01 → 2026-09; size drops 3 MB → 841 KB from 2024-10 | `FI/DOC/LAMINA/DADOS/lamina_fi_YYYYMM.zip` |
| FI perfil mensal | 2019-01 → 2026-09 | `FI/DOC/PERFIL_MENSAL/DADOS/perfil_mensal_fi_YYYYMM.csv` |
| FI extrato | yearly 2015–2026 + `extrato_fi.csv` (33 MB, rewritten daily) | `FI/DOC/EXTRATO/DADOS/` |
| FI balancete | 2015-01 → 2026-09 (+ HIST/) | `FI/DOC/BALANCETE/DADOS/balancete_fi_YYYYMM.zip` |
| FI eventual | yearly 2005–2026 | `FI/DOC/EVENTUAL/DADOS/eventual_fi_YYYY.csv` |
| FI compl | 2018-01 → 2019-04 only | `FI/DOC/COMPL/DADOS/` |
| FI entrega documento | HIST 2021–2024; 2025-01 → 2026-11 | `FI/DOC/ENTREGA/DADOS/` |
| FIDC inf_mensal | 2025-01 → 2026-09 (+ HIST/) | `FIDC/DOC/INF_MENSAL/DADOS/inf_mensal_fidc_YYYYMM.zip` |
| FIP | trimestral 2010–2023; quadrimestral 2024–2026 | `FIP/DOC/INF_TRIMESTRAL/DADOS/`, `FIP/DOC/INF_QUADRIMESTRAL/DADOS/` |

## 7. Open questions
- Do FIEs appear in INF_DIARIO? FIE layouts; cause of the 2024-10 lâmina size drop *(not verified)*.
