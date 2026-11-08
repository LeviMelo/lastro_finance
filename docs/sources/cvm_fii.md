# cvm_fii — CVM: informes FII (mensal / trimestral / anual); FIAGRO measured, not parsed

**Tier:** P. **Recon:** 2026-11-07. **Parser:** `src/fin/ingest/cvm_funds.py` (`CvmFii`). **Fixtures:** `tests/fixtures/cvm_fii/`.

Every statement was measured on 2026-11-07 against real files unless marked *(from docs)*.

## 1. Access
- Same CVM tree and headers as `cvm_fi_inf_diario.md` §1; zips are `application/zip`, ETag/Last-Modified/304 work, the generic UA is fine.

## 2. Datasets (yearly zips 2016-2026)
| dataset_id (staging) | member of the zip | rows measured | key |
|---|---|---|---|
| monthly_general | `inf_mensal_fii_geral_YYYY.csv` | 11,785 in 2026 (1,428 funds, Jan-Oct) | cnpj, reference_date, version |
| monthly_summary | `inf_mensal_fii_complemento_YYYY.csv` | same | same |
| monthly_balance | `inf_mensal_fii_ativo_passivo_YYYY.csv` | same | same |
| quarterly_general / quarterly_property / quarterly_asset | `inf_trimestral_fii_{geral,imovel,ativo}_YYYY.csv` | 2,760 / 11,410 / 25,930 in 2026 | same |
| annual_general | `inf_anual_fii_geral_YYYY.csv` | 416 in 2026 | same |
- Zip sizes 2016-2026: mensal 9.4 MB (58 KB in 2016 to 1.5 MB in 2025), trimestral 15.7 MB, anual 18 MB. Raw as members, zstd-9: 34 MB for all years of the three; staging a few MB per year.
- Not parsed: the 13 other quarterly members (alienacao/aquisicao, garantia, complemento, direito, desempenho, contrato, inquilino, rentabilidade_efetiva, resultado_contabil_financeiro, terreno) and the 9 other annual ones (ativo_*, complemento, **diretor_responsavel with CPF and e-mail**, distribuicao_cotistas, experiencia_profissional, prestador_servico, processo). Quarterly contracts/tenants and the result statement are the next candidates.
- FIAGRO: `FIAGRO/DOC/INF_MENSAL/DADOS/inf_mensal_fiagro_YYYYMM.zip` (2025-05 to 2026-10, 18 zips, 0.8 MB): members `inf_mensal_fiagro_YYYYMM.csv` and `..._subclasse_...`, a different layout (CNPJ_Classe digits only, Nome_Classe, Regra_Anexo...). Not parsed.

## 3. Layout and units (header checked in code)
- `;`, CRLF, cp1252, ISO dates, `.` decimal; some values in exponent notation (`8.17058518048235E-06`).
- **Header eras:** files 2016-2020 use `CNPJ_Fundo`, `Nome_Fundo` and have no `Tipo_Fundo_Classe`; files 2021-2026 use `CNPJ_Fundo_Classe`, `Nome_Fundo_Classe`, `Tipo_Fundo_Classe` (Classe/Fundo). The balance sheet lacks `CRI_CRA`, `LCI_LCA` in 2016-2018. All 33 zips (2016-2026) parse with 0 quarantined: monthly 83,652 rows per member, quarterly property 154,362, asset 252,783, annual general 6,879.
- **Numeric columns are nvarchar in the source (meta): float noise is real.** Quotas issued come as `1324930.00003248`, BRL values with up to 16 decimals, NAV per quota `0.0638946093935791`. Parsed as wide Decimals (BRL scale 16, quota and ratio scale 20), unrounded; the parser fails if a value does not fit.
- `Percentual_*` of `complemento` are **fractions** (HGLG11 dividend yield Sep-2026 `0.007052` = 0.71%). Quarterly property ratios are fractions in 2026 (`Percentual_Vacancia 0.1039`), but `aquisicao_terreno` carries `6.43` (a percent): check the scale of any member not parsed yet.
- `Data_Referencia`: first day of the reference month (monthly), quarter end (quarterly). `Data_Entrega` (geral) is the delivery date = knowledge time: median 44 days after the 1st of the reference month (about 14 after month end), p90 45-47.
- Identity: `CNPJ_Fundo_Classe` formatted `00.000.000/0000-00`; `Codigo_ISIN` is empty on 14-15 % of rows and no ticker appears anywhere in these files (tickers come from B3 instruments).
- Spot (2026-09, `inf_mensal_fii_complemento_2026.csv`): HGLG11 (CNPJ 11.728.688/0001-47) NAV per quota 165.476630173739, net assets 7,546,017,797.39, quotas 45,601,713, holders 613,837, dividend yield 0.007052; KNRI11 (12.005.956/0001-65) NAV per quota 163.639521340679. NAV x quotas = net assets to 1e-9. The staged parquet equals the file.
- Negative net assets are real (164 monthly rows in 2026; fund 00.613.094/0001-74, NAV per quota -33.26): kept, no rule.

## 4. Ephemerality and restatements
- 2021-2026 zips are rewritten weekly (LM 2026-11-07 for all). A document has `Versao` 1..6, and the files mostly hold only the latest version (2026: 0 duplicated (cnpj, month); 2025: 16), so a restatement overwrites the earlier number: every ETag is archived (members as deltas, staging keeps changed rows only, ADR-0014).
- Plan: backfill takes every year once; the daily job asks the current and previous year weekly (conditional GET) and older years monthly; years never seen before are taken only by backfill unless within the trailing year.

## 5. Open questions
- Whether 2016-2020 files keep superseded versions (not inspected); FII DFIN; the other quarterly/annual members; a FIAGRO parser.
