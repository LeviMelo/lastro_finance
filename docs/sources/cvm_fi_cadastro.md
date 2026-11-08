# cvm_fi_cadastro — CVM: cadastro de fundos / registro fundo-classe-subclasse (FI/CAD)

**Tier:** P. **Recon:** 2026-11-07; layouts, parsers and the CVM 175 bridge measured 2026-11-08 on the archived files
(raw sha256 `a432031e…` cad_fi, `9e680a63…` cad_fi_hist, `07bd1ec3…` registro_fundo_classe).
**Fixtures:** `tests/fixtures/cvm_fi_cadastro/` (README lists URL, sha256, lines kept; the `Diretor` column is blanked).
Parsers: `ingest/cvm_fi_cad.py`; core: `core/funds.py`; decision: ADR-0025.

## 1. Access
- Same CVM tree and header behaviour as `cvm_fi_inf_diario.md` §1 (ETag/Last-Modified, 304 on conditional GET, Range 206, Cloudflare 4 h cache).

## 2. Datasets
| dataset_id | what | size / rows (2026-11-07) | cadence | URL |
|---|---|---|---|---|
| cad_fi | legacy fund register, one row per registration (CD_CVM) | 17.9 MB; 46,805 rows, 41,102 CNPJs | daily | `FI/CAD/DADOS/cad_fi.csv` |
| cad_fi_hist | legacy attribute history, 19 members (one per attribute) | 18.7 MB zip; `sit` 146,264 rows, `denom_social` 152,870 | daily | `FI/CAD/DADOS/cad_fi_hist.zip` |
| registro_fundo_classe | CVM 175 register, 3 members | 6.9 MB zip | daily | `FI/CAD/DADOS/registro_fundo_classe.zip` |
| meta_* | field layouts (txt in zip), kept raw only | 7.6 KB, 2.2 KB | — | `FI/CAD/META/meta_cad_fi.zip`, `meta_registro_fundo_classe.zip` |

`registro_fundo_classe.zip`: `registro_fundo.csv` 91,046 rows (89,891 funds; a fund repeats once per extra
registered manager), `registro_classe.csv` 37,075 (37,070 classes; repeats once per extra auditor/controller),
`registro_subclasse.csv` 11,686 (all distinct `ID_Subclasse`).

## 3. Layout and quirks
- cp1252, `;`, CRLF, header on line 1; a few stray `"` in names (read without quoting). Dates `YYYY-MM-DD`; money with
  `.` decimals. CNPJs are punctuated in `cad_fi*` and 14 digits in `registro_*`; staging stores 14 digits.
- Parsed to staging: `fund` (cad_fi), `fund_history` (12 of 19 members in long form: `sit`, `classe`, `denom_social`,
  `denom_comerc`, `condom`, `fic`, `exclusivo`, `publico_alvo`, `trib_lprazo`, `rentab`, `admin`, `custodiante`;
  954,698 rows), `registered_fund`, `registered_class`, `registered_subclass`. Reparse: all rows in, none
  quarantined (`fund`: 6 "EM ANÁLISE" rows without CD_CVM are kept with a null code).
- **Not parsed, on purpose:** `DIRETOR`/`Diretor` and `cad_fi_hist_diretor_resp` (a named person); a manager with
  `PF` person type loses name and CPF (47 rows of cad_fi, 226 of registro_fundo; the PJ ones keep both);
  controller and auditor columns and members (a controller can be a person); fees (`taxa_*`) and the exercise dates.
- cad_fi keeps almost only dead registrations: 46,590 of 46,805 rows are `CANCELADA`, 21 `EM FUNCIONAMENTO NORMAL`.
  A fund adapted to Res. 175 shows there as cancelled; its live history is in `cad_fi_hist` and `registro_*`.

## 4. Identity (CVM 175)
- `registro_fundo.CNPJ_Fundo` ↔ `registro_classe.CNPJ_Classe` through `ID_Registro_Fundo`; subclasses by
  `ID_Registro_Classe`. `Data_Adaptacao_RCVM175` is on the fund and is filled for 45,035 funds, new ones included.
- 37,653 of the 37,803 classes of adapted funds have the CNPJ of their fund; 55 funds have more than one class.
  Informe diário: `CNPJ_FUNDO_CLASSE` = class CNPJ, `TP_FUNDO_CLASSE` = `CLASSES - FIF` (or `CLASSE FIF/FAPI`).

## 5. Ephemerality
- `cad_fi.csv` and `registro_fundo_classe.zip` are single overwritten files with no dated copies → **ephemeral
  snapshots: archive daily** (cheap with ETag/304). Staging keeps only changed rows (ADR-0014).

## 6. The CVM 175 bridge, measured 2026-11-08 (ADR-0025)
Lineage rows 27,461: `same_cnpj` 27,399, `class_own_legacy` 19, `fund_single_class` 22, `fund_multi_class` 21.
Test on the daily quota (last legacy-typed row before the first class-typed row; ≤ 3 business days apart):

| status | bridges | meaning |
|---|---|---|
| clean | 18,590 | quota moves ≤ 1 % |
| moved | 1,381 | 1–5 %, within 5 robust sigmas of the fund's own daily moves |
| jump | 182 | beyond both |
| gap | 64 | > 3 business days between the last legacy and first class report |
| no_legacy_series | 5,521 | legacy CNPJ never reported before the class type (5,488: class-typed from the first row) |
| no_class_series | 1,723 | 1,370 CNPJs never appear in the daily report, 353 only under legacy types |

20,217 testable, **98.8 % continuous**; 19,930 of them switch on the next business day (gap 0), 215 after one.
Switch dates cluster at month starts (2024-10-01 for most); the median lag from `Data_Adaptacao_RCVM175` is 17 days.
- **Jumps (182, all switching in 2024–2025):** 77 are 1–2 %, 59 are 2–5 %, 28 are 5–20 %, 14 are 20–90 % and 4 above
  90 %. The large ones are re-denominated quotas: pre-operational placeholders (0.00001 → 782.85), ×2 (958.6 → 1,914),
  ×0.26 (2.23 → 0.58). 12 of the 182 have a flat legacy series (sigma 0), so any move counts.
- **Gaps (64):** 53 have ≥ 19 business days without any report around the switch; 19 of the 64 still move ≤ 1 %.
- **Golden fund** SPECIAL RENDA FIXA REFERENCIADO DI FIF (CNPJ 01.597.187/0001-15; `ID_Registro_Fundo` 28272,
  class 142, `same_cnpj`): legacy registration under CD_CVM 9016 cancelled 2005-03-07, live one 23710 since;
  `Data_Adaptacao_RCVM175` 2024-08-29 (the name gains "FUNDO DE INVESTIMENTO FINANCEIRO RESPONSABILIDADE LIMITADA"
  that day in `cad_fi_hist`); class registered 2024-08-29 (class CD_CVM 59900). Informe diário: `FI` 2024-09-27
  362.394415, 2024-09-30 362.546162; `CLASSES - FIF` 2024-10-01 362.691560 (+0.04 %), 2024-10-02 362.844750.
  Unit test: `tests/unit/test_funds.py::test_golden_fund_quota_continues_across_the_switch`.

## 7. Open questions
- Whether the 5,521 funds without a legacy series are all funds that started under Res. 175 with an old CNPJ
  (cad_fi_hist's `sit` lists them), or hide older series published under another CNPJ.
- The 19 `class_own_legacy` and 21 `fund_multi_class` cases are few; the latter are not claimed continuous.
- `cad_fi_hist` members not parsed (fees, exercise dates, tax) are archived raw and can be added from raw.
