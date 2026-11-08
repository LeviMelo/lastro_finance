# cvm_fi_cda — CVM: Composição e Diversificação das Aplicações (FI/DOC/CDA)

**Tier:** P. **Recon:** 2026-11-07. **Parser:** `src/fin/ingest/cvm_funds.py` (`CvmFiCda`). **Fixtures:** `tests/fixtures/cvm_fi_cda/`.

Every statement was measured on 2026-11-07 against real files unless marked *(from docs)*.

## 1. Access
- Same tree and headers as `cvm_fi_inf_diario.md` §1. Range requests read zip directories (sizes and headers of old files).

## 2. Datasets
| item | measured |
|---|---|
| monthly zips | `FI/DOC/CDA/DADOS/cda_fi_YYYYMM.zip`, 2023-01..2026-10 (46, 1,034 MB; 19.6 MB in 2023-01, 26 MB for full months, 2 MB for 2026-10) |
| yearly HIST | `.../DADOS/HIST/cda_fi_YYYY.zip`, 2005-2022 (18, 1,188 MB; 28 MB in 2005, 147 MB in 2022); members are **yearly** (`cda_fi_BLC_2_2022.csv` = 642 MB unzipped), partition `year=YYYY` |
| members of a month (2026-10) | `cda_fi_BLC_1..8`, `cda_fi_PL`, `cda_fi_CONFID`, `cda_fie`, `cda_fie_CONFID` (2023-01..2024-01 also `cda_fiim`, index funds with an ID_DOC) |
| meta | `META/meta_cda_fi_txt.zip` (10 KB, 12 txt, latin-1): QT_POS_FINAL numeric(21,6), VL_* numeric(17,2), PR_* numeric(9,6), VL_ATIVO_EXTERIOR float(53) |
- Parsed (staging, partition `month=YYYYMM`): `position` = BLC_1..8 as one union table with a `block` column (1 títulos públicos, 2 cotas de fundos, 3 swaps, 4 ações e debêntures, 5 CDB/RDB, 6 crédito privado, 7 exterior, 8 outros); `net_assets` = PL. Not parsed: CONFID (values only), `cda_fie` and `cda_fie_CONFID` (FIE funds, see `cvm_fie`), `cda_fiim`, meta.
- Rows: 2026-07 (full) 1,000,546 positions and 25,628 funds; 2024-01 781,736 and 26,215; 2026-10 (partial, 2 MB) 69,010. 3.26 M positions parsed from 2023-01, 2023-12, 2024-01 and 2026-07 with 0 quarantined.

## 3. Layout (checked in code)
- Every BLC member = 16 common columns (`TP_FUNDO_CLASSE, CNPJ_FUNDO_CLASSE, DENOM_SOCIAL, DT_COMPTC, TP_APLIC, TP_ATIVO, EMISSOR_LIGADO, TP_NEGOC, QT_VENDA_NEGOC, VL_VENDA_NEGOC, QT_AQUIS_NEGOC, VL_AQUIS_NEGOC, QT_POS_FINAL, VL_MERC_POS_FINAL, VL_CUSTO_POS_FINAL, DT_CONFID_APLIC`) + block columns (ISIN and SELIC code, held fund CNPJ, swap code, asset code, issuer, index and rate, rating, foreign asset); the lists are in `cvm_funds._BLOCKS`.
- **Header eras:** up to 2023-11 `TP_FUNDO;CNPJ_FUNDO`, BLC_2 `CNPJ_FUNDO_COTA;NM_FUNDO_COTA` (no subclass); from 2023-12 `TP_FUNDO_CLASSE;CNPJ_FUNDO_CLASSE`, BLC_2 `CNPJ_FUNDO_CLASSE_COTA;ID_SUBCLASSE;NM_FUNDO_CLASSE_SUBCLASSE_COTA`. The 2022 HIST member headers are the legacy layout (only read, not parsed).
- cp1252, `;`, CRLF, `.` decimal, ISO dates. Quantities have 6 decimals, values 2. `PR_INDEXADOR_POSFX` is a percentage of the index (102.6 = 102.6% of DI), `PR_TAXA_PREFX` a rate in percent as written.
- **Personal data:** BLC_6/8 carry `PF_PJ_EMISSOR`, `CPF_CNPJ_EMISSOR` and `EMISSOR`: natural-person issuers appear (3 rows in 2023-01 BLC_6, 6 in 2026-07; a CPF and a person's name). The parser nulls issuer tax id and name for PF or any CPF-looking id and keeps PJ CNPJ only. `DENOM_SOCIAL` (fund name) is kept in `net_assets` only, not on every position.
- Spot (2026-10 fixtures): BLC_1 first row LFT BRSTNCLF1RH3, SELIC 210100, 20 units, market value 403,934.95, maturity 2027-09-01; BLC_5 first row CDB at 102.6% of DI1. PL of 00.017.024/0001-53: 1,228,168.72.

## 4. Footprint (zstd-9 raw, parquet staging, measured on 2024-01 and 2026-07)
- Full month: csv 223-301 MB, raw 16.5-20.6 MB, staging 14-18 MB (0.76 and 0.66 of the zip). Projection: monthly 2023-01..2026-10 raw ~0.78 GB + staging ~0.68 GB; HIST 2005-2022 raw ~0.90 GB + staging ~0.78 GB (estimate with the same ratios). A yearly BLC member of up to 640 MB needs several GB of RAM, so HIST is off by default (`hist=True` takes it).

## 5. Ephemerality
- Not ephemeral; revised in place. Recent months grow as late filings arrive (2026-10 is 2 MB on 07-Nov, 2026-08/09 15 MB, full months 26 MB) and frozen months get bulk rewrites (2024-02..2025-01 on 18-Feb-2026): every ETag is stored and staging keeps only changed rows. Plan: months 0-1 daily, up to 4 months old weekly, older monthly; never-seen old months only by backfill.

## 6. Open questions
- HIST layouts before 2022 and a streaming parse for the 640 MB members; the `DT_CONFID_APLIC` window; how to reconcile the CDA PL with the daily NAV (dq_finding).
