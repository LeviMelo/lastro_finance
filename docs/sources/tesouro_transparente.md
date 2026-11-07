# tesouro_transparente — Tesouro Nacional: Tesouro Direto open data (taxas e PU)

**Tier:** P. **Recon date:** 2026-11-07. **Fixture:** `tests/fixtures/tesouro_transparente/` (header + all rows of one LTN 01/01/2027, one NTN-B 15/05/2035, one LFT 01/03/2027; 7,252 rows, 622 KB).

## 1. Access
- CKAN, no auth, ODbL. `https://www.tesourotransparente.gov.br/ckan/api/3/action/package_show?id=taxas-dos-titulos-ofertados-pelo-tesouro-direto` → 200 (browser UA; generic `curl/8` UA also 200 on the CSV HEAD). Resources: PDF metadata (`taxa.pdf`) + CSV.
- CSV: `https://www.tesourotransparente.gov.br/ckan/dataset/df56aa42-484a-4a59-8184-7676580c81e3/resource/796d2059-14e9-44e3-80c9-2d9e30b405c1/download/precotaxatesourodireto.csv`
- **Update behaviour:** `Last-Modified: Fri, 06 Nov 2026 10:29:14 GMT` (matches CKAN `last_modified`), `ETag: "1793960954.68-14663350"`, `Cache-Control: no-cache`; conditional GET works (`If-None-Match` and `If-Modified-Since` → 304). File is a full re-upload (whole history each time); modified 2026-11-06 morning with last Data Base 2026-11-05, i.e. D+1 morning lag.

## 2. Datasets
| dataset_id | granularity | history | cadence | URL |
|---|---|---|---|---|
| taxas (PrecoTaxaTesouroDireto.csv) | title × maturity × day, 14.7 MB, 178,246 rows | **2004-12-31 → 2026-11-05** (5,453 distinct days, ~250/yr). **Not 2002** (PLAN/brief) | daily, next morning | above |

Other Tesouro Direto datasets in the same CKAN (package_search `tesouro direto`, 6 hits; all ODbL, header seen via Range):
- `vendas-do-tesouro-direto` — `vendastesourodireto.csv` 7.5 MB, sales per title/maturity (columns not read).
- `resgates-do-tesouro-direto` — 3 CSVs: `cupomjurostesourodireto.csv` (coupon payments), `recomprastesourodireto.csv` (buy-backs), `vencimentostesourodireto.csv` (maturities).
- `estoque-do-tesouro-direto` — `estoquetesourodireto.csv` 718 KB; `Tipo Titulo;Vencimento do Titulo;Mes Estoque;PU;Quantidade;Valor Estoque`, monthly (from 09/2020 in first rows).
- `operacoes-do-tesouro-direto` — investor-level operations, per-year CSV/ZIP 2014–2026 (40 MB–1 GB each) + `base completa` GZ 1.2 GB; `Codigo do Investidor;Data da Operacao;Tipo Titulo;Vencimento do Titulo;Quantidade;Valor do Titulo;Valor da Operacao;Tipo da Operacao;Canal da Operacao`. Not needed by LASTRO. 2025 rows use title name `NTN-B1` (sample only).
- `investidores-do-tesouro-direto` — investor registry, up to 898 MB GZ; personal-data-adjacent, skip.

## 3. Layout (confirmed on full file)
`Tipo Titulo;Data Vencimento;Data Base;Taxa Compra Manha;Taxa Venda Manha;PU Compra Manha;PU Venda Manha;PU Base Manha` — 8 fields in every row, none empty.
```
Tesouro Selic;01/03/2027;05/11/2026;0,02;0,03;20240,75;20229,76;20229,76
Tesouro Prefixado;01/01/2027;05/11/2026;13,58;13,70;980,98;980,32;980,32
```
- Rates % a.a. (2 dp; for Selic = spread over Selic), PUs BRL (2 dp). `PU Base Manha` = reference PU of the morning (as published; relation to buy/sell not analysed).
- Title names as written (exact strings, row counts): `Tesouro Prefixado` (LTN, 28,285), `Tesouro Prefixado com Juros Semestrais` (NTN-F, 27,457), `Tesouro IPCA+` (NTN-B principal, 19,026; from 2005-07-18), `Tesouro IPCA+ com Juros Semestrais` (NTN-B, 44,253), `Tesouro Selic` (LFT, 21,521), `Tesouro IGPM+ com Juros Semestrais` (NTN-C, 15,827; maturity 01/01/2031 still quoted on 2026-11-05, PU ~7,981), `Tesouro Educa+` (14,357; from 2023-08-01), `Tesouro Renda+ Aposentadoria Extra` (7,520; from 2023-01-30). No code column: map name → type by this table.

## 4. Quirks
- ASCII only (no accents in titles); `;` separator, no quotes; decimal comma; dates `dd/mm/yyyy`; **LF** line endings; no thousands separator.
- **Sorted newest Data Base first** (strictly descending); no duplicate (title, maturity, date) keys.
- Zero values are real or sentinel: Taxa Compra = `0,00` in 7,482 rows (7,467 are Tesouro Selic, spread rounds to 0 — genuine); 49 rows with PU Compra `0,00`, 48 with PU Venda `0,00`, 29 PU Base `0,00` (probably unavailable-for-sale/bad rows; not investigated).
- Rows exist for all maturities listed that day (incl. ones closed to purchase) *(not verified)*; dataset is the *offered* bonds' morning prices, not closing secondary-market (ANBIMA is that).
- Whole history re-uploaded each time; past values could be revised silently → keep sha256 per download.

- **Zero PUs, read (2026-11-07):** the `0,00` buy/sell PUs fall on a title's last days before maturity (e.g. NTN-F
  2023-01-01 on 2022-12-29: buy 0,00, sell and base 1047,70): that side was not offered. Parsed as null; a zero base
  PU (29 rows) is quarantined. Two consecutive daily files agree on all 178,197 shared rows and add 58 rows (one day).
- 8 titles: Prefixado, Prefixado com Juros Semestrais, IPCA+, IPCA+ com Juros Semestrais, Selic, IGPM+ com Juros
  Semestrais (2004–), Renda+ Aposentadoria Extra (2023-01-30–), Educa+ (2023-08-01–).

## 5. Identity fields
`Tipo Titulo` + `Data Vencimento` → Tesouro instrument (no SELIC code, no ISIN). Join to ANBIMA by type + maturity.

## 6. Ephemerality
Not ephemeral: full history on every download. Archive the whole file when `Last-Modified` changes (≈ daily, 14 MB).

## 7. Open questions
- Does anything exist before 2004-12-31 (brief says 2002)? Not in this file; Metadados PDF not read.
- Meaning/units of `PU Base Manha`, and cause of zero PUs.
