# cvm_dfp_itr - CVM: DFP and ITR statements

**Tier:** P. **Recon date:** 2026-11-07. **Fixture:** `tests/fixtures/cvm_dfp_itr/` (DFP 2024 index, BPA_con, DRE_con rows of Itau and Petrobras, 80 KB; README there).

Every statement was measured on 2026-11-07 against a real response unless marked *(not verified)*.  The DFP 2024 zip was downloaded and read in full; **ITR was not opened** (all ITR statements below are *(not verified)*).

## 1. Access
- HTTPS file tree https://dados.cvm.gov.br/dados/CIA_ABERTA/ (nginx autoindex behind Cloudflare). No auth. A generic UA worked; no blocking was seen.
- Headers: `Last-Modified`, `ETag` (nginx style, mtime-hex/size-hex) and `Content-Length`. `If-None-Match` and `If-Modified-Since` both return **304**. `Accept-Ranges: bytes` gives 206, so single zip members can be read without the whole zip (central directory first, then member ranges). Cloudflare `Cache-Control: max-age=14400`.
- The autoindex shows times in BRT (UTC-3), and Last-Modified is in GMT.
- CKAN API (`/api/3/action/package_list`, `package_show`): *(not verified)*.
- Regeneration seen: the current year and the four years before it were all rewritten on 2026-11-01 (a Sunday, about 07:00-08:50 BRT), so the cycle looks weekly *(cadence inferred from one listing)*. Older years are frozen, e.g. 2021 last written 2025-12-28 and 2020 on 2024-12-29. So a year is rewritten for about 5 years after it ends.

## 2. Datasets
| dataset_id | history | URL |
|---|---|---|
| dfp_cia_aberta | 2010-2026 (8-13 MB; 2026 is 238 KB) | DOC/DFP/DADOS/dfp_cia_aberta_YYYY.zip; DOC/DFP/META/meta_dfp_cia_aberta_txt.zip |
| itr_cia_aberta | 2011-2026 (22-31 MB) | DOC/ITR/DADOS/itr_cia_aberta_YYYY.zip; DOC/ITR/META/meta_itr_cia_aberta_txt.zip |

## 3. Layout (DFP 2024, zip 13.4 MB, 19 members; cp1252, ';', CRLF, header line, no BOM)
- Members: index `dfp_cia_aberta_2024.csv` (873 rows); statements `dfp_cia_aberta_<ST>_<con|ind>_2024.csv` for ST = BPA, BPP, DRE, DRA, DFC_MI, DFC_MD (tiny: 155-199 KB), DMPL, DVA; plus `composicao_capital` and `parecer` (auditor opinion, 15 MB of text). Layout: `DOC/DFP/META/meta_dfp_cia_aberta_txt.zip` (11 small field-dictionary txt files, 6.8 KB).
- **Index** columns: `CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;CD_CVM;CATEG_DOC;ID_DOC;DT_RECEB;LINK_DOC`. CD_CVM is 6 digits zero-padded (`019348`). **`DT_RECEB` is the delivery (knowledge) date, date only** (2024-05-09 to 2026-04-17 in this file). `LINK_DOC` = `http://www.rad.cvm.gov.br/ENETCONSULTA/frmDownloadDocumento.aspx?CodigoInstituicao=1&NumeroSequencialDocumento=<ID_DOC>` (not fetched). Sample: `60.872.504/0001-23;2024-12-31;1;ITAU UNIBANCO HOLDING S.A.;019348;DFP;144592;2025-02-05;...`; Petrobras `33.000.167/0001-01;2024-12-31;1;...;009512;DFP;145077;2025-02-26`.
- **Statement** columns (BPA/BPP): `CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;CD_CVM;GRUPO_DFP;MOEDA;ESCALA_MOEDA;ORDEM_EXERC;DT_FIM_EXERC;CD_CONTA;DS_CONTA;VL_CONTA;ST_CONTA_FIXA`. DRE, DFC and DRA add `DT_INI_EXERC` after ORDEM_EXERC. DMPL adds `DT_INI_EXERC` and `COLUNA_DF` (equity column) before CD_CONTA. `composicao_capital` has no CD_CVM: `QT_ACAO_{ORDIN,PREF,TOTAL}_CAP_INTEGR` and `..._TESOURO` (whole shares, unscaled).
- Domains measured (BPA_con): `MOEDA` always `REAL`; `ESCALA_MOEDA` `MIL` (98 %) or `UNIDADE` (2 %); `ORDEM_EXERC` `ÚLTIMO` / `PENÚLTIMO` (each row exists for the current and the prior period, so the prior year is restated as filed in this document); `ST_CONTA_FIXA` S/N. `GRUPO_DFP` is the statement name (`DF Consolidado - Balanço Patrimonial Ativo`).
- `VL_CONTA` is a plain decimal with a dot, 9-10 decimals, negative with `-` (no thousand separators), never empty in the files checked. **Scale: multiply by 1000 when `ESCALA_MOEDA = MIL`** (Itau total assets `2854475000.0` = R$ 2.85 trillion in thousands).
- Samples verbatim: `00.000.000/0001-91;2024-12-31;1;BCO BRASIL S.A.;001023;DF Consolidado - Balanço Patrimonial Ativo;REAL;MIL;ÚLTIMO;2024-12-31;1;Ativo Total;2398719197.0000000000;S`; DRE: `...;REAL;MIL;ÚLTIMO;2024-01-01;2024-12-31;3.01;Receitas de Intermediação Financeira;273505274.0000000000;S`.

## 4. Quirks
- **Versions**: the index lists **every** delivered version (`VERSAO` 1-4: 710 v1, 139 v2, 22 v3, 2 v4; 139 company/period keys have more than one; each version has its own `ID_DOC` and `DT_RECEB`; BRB: v1 2025-04-09, v2 2025-04-10, v3 2025-06-30). The **statement files hold only the latest version** per company and period (704 of 704 BPA_ind keys equal the index maximum; no key has two versions in a data file). Superseded numbers are not published here, so archive each weekly file to keep restated-from values; the index alone gives the knowledge time of each version.
- The same file also holds periods other than 12-31 (fiscal years ending 03-31, 06-30, 02-28: 12 index rows) and DT_RECEB up to 2026-04-17, i.e. late re-presentations. 5 index keys have no individual statements.
- Consolidated covers 467 companies, individual 704 (consolidated is filed by fewer companies).
- **Banks vs industrials** (Itau vs Petrobras, consolidated, current period): CD_CONTA codes are the same scheme (`1`, `1.01`, `3.01`...) but the **meaning of the same code differs**. Itau BPA: 41 rows (including 1.01 Caixa, 1.02 Ativos Financeiros, 1.03 Tributos Diferidos, 1.04 Outros Ativos, 1.05 Investimentos, 1.06 Imobilizado, 1.07 Intangível), no current/non-current split. Petrobras BPA: 65 rows, `1.01 Ativo Circulante`, `1.02 Ativo Não Circulante`. DRE: Itau `3.01 Receitas da Intermediação Financeira`, `3.02 Despesas da Intermediação`, `3.03 Resultado Bruto Intermediação`, `3.04 Outras Despesas/Receitas Operacionais`, `3.05 Resultado antes dos Tributos`, `3.06 IR e CSLL`, `3.07..3.09` net result, `3.99` EPS; Petrobras `3.01 Receita de Venda`, `3.02 Custo`, `3.03 Resultado Bruto`, `3.04 Despesas/Receitas Operacionais`, `3.05 EBIT-like`, `3.06 Resultado Financeiro`, `3.07 LAIR`, `3.08 IR`, `3.09`, `3.10`, `3.11 Lucro/Prejuízo Consolidado`. Mapping to a canonical income line must be keyed on (sector layout, CD_CONTA) or on DS_CONTA, not on CD_CONTA alone. Both: `ESCALA_MOEDA = MIL`, VERSAO 1. Net profit consolidated 2024: Itau `42128000` (thousands), Petrobras `37009000` (3.11 includes minorities).
- `3.99` is the EPS header; the per-share value may sit in sub-accounts (`3.99.01.01`...). Itau 3.99 shows `16.7200000000` with `ST_CONTA_FIXA N`, meaning not checked against the filing *(not verified)*.
- Statement-file encoding is cp1252 (all rows decode; `ÚLTIMO`/`PENÚLTIMO` accented); DS_CONTA text varies in wording across companies for non-fixed accounts (`ST_CONTA_FIXA = N`: 25 % of BPA rows).

## 5. Identity fields
`CNPJ_CIA` (formatted `00.000.000/0001-91`), `CD_CVM` (6-digit string in index and statements; no CD_CVM in composicao_capital), `ID_DOC` (index only, document key; join statements to the index on CNPJ_CIA + DT_REFER + VERSAO).

## 6. Ephemerality
Persistent yearly files, regenerated weekly for the last years (Last-Modified of the 2024 zip: 2026-11-01). Only the latest version of each statement survives in the data files, so older versions are lost unless the weekly file is archived.

## 7. Open questions
- ITR (`itr_cia_aberta_YYYY.zip`): members, quarterly DT_INI/DT_FIM, the index `CATEG_DOC` = ITR and whether Q4 is derived, all *(not verified)*.
- Whether LINK_DOC (ENETCONSULTA host) still resolves and what it returns (not fetched).
- Whether the 2024 file's prior-period (PENÚLTIMO) rows equal the restated 2023 numbers; and how much the PENÚLTIMO values differ from the 2023 DFP.

## 8. Parsed (2026-11-07, `ingest/cvm_statements.py`)
- Every member header is identical across DFP 2010–2026 and ITR 2011–2026 (33 zips); all decode as cp1252. ITR has
  the same members as DFP (its auditor member's 5th column is `TP_RELAT_ESP`, DFP's `TP_RELAT_AUD`).
- 66,783,329 statement lines, 0 quarantined; 49,787 delivered document versions of 1,224 companies; 18,495
  share-capital rows. Staging 231 MB; about 2 s per DFP zip.
- `composicao_capital`: 6 rows with a negative treasury count (Bradesco DFP 2022 and ITR 2024-Q1, Azzas 2020,
  Ourofino 2023) are quarantined. **The unit of the counts is not stated**, and companies use both: against B3's current
  counts, 201 of 340 issuers file units, 93 thousands, some switch (Bradesco: thousands to 2023, units from 2024).
  The unit is inferred per filing (ADR-0020, core `share_count`).
- `composicao_capital` exists from 2020 only: the 2019 DFP zip has statements, index and `parecer`, but no
  share counts (checked 2026-11-07). Valuation therefore starts in 2020 (ADR-0021).
