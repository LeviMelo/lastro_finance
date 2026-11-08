# anbima_debentures — ANBIMA: Mercado Secundário de Debêntures (taxas médias)

**Tier:** P. **Recon date:** 2026-11-07. **Fixture:** `tests/fixtures/anbima_debentures/db261106.txt` (full day, 178 KB).

## 1. Access
- Form `https://www.anbima.com.br/informacoes/merc-sec-debentures/` ("últimos 5 dias úteis"; `Dt_Ref_Ver=20261029`). Retifications are posted on the page (HAPV15/HAPV17 of 2026-10-29 and FISI15 of 2026-08-21: "retificadas e não serão disponibilizados novos arquivos").
- Files: **`https://www.anbima.com.br/informacoes/merc-sec-debentures/arqs/dbYYMMDD.txt`** and `.../arqs/dYYmonDD.xls` (pt month: `d26nov06.xls`, 2.2 MB). The links printed on the page point at `/merc_sec_debentures/arqs/…`, which **404s** for current dates; the alias `arqs/Db_txt.txt` also 404.
- Measured: db261106, 05, 04, 03, 261030, 261029 → 200 (~178 KB each; Last-Modified Fri 06 Nov 22:57 GMT for 261106, ETag `"c05b2941426edd1:0"`); 261102 (holiday), 261028, 261027, 260102, 240102, 180102 → 404; xls 26nov06 and 26out29 → 200, 26out28 → 404. Window = 6 business days, as titulos_publicos.

## 2. Datasets
| dataset_id | granularity | history | cadence |
|---|---|---|---|
| db_txt / d_xls | debenture × day (DI, IGP-M, IPCA indexed) | **rolling 6 business days** | daily evening (Last-Modified 22:51–23:10 GMT = ~20h BRT) |

## 3. Layout (txt; Latin-1, CRLF, `@`-separated; title line, blank line, header)
`Código@Nome@Repac./  Venc.@Índice/ Correção@Taxa de Compra@Taxa de Venda@Taxa Indicativa@Desvio Padrão@Intervalo Indicativo Minimo@Intervalo Indicativo Máximo@PU@% PU Par / % VNE@Duration@% Reune@Referência NTN-B`
```
AALM12@AURA ALMAS MINERACAO S.A. (*)@02/10/2030@DI + 1,6%@1,0168@0,796@0,8944@0,0216@0,8727@0,9161@1027,456224@101,4057@505,67@@
ADPA21@AGUAS DO PARA A SPE S.A. (*)@27/11/2027@DI + 2,85%@--@2,3131@2,8741@0,0544@2,8196@2,9286@1061,885993@99,977@247,9@5@
```
Decimal comma, dates dd/mm/yyyy, `--` = no value, footnote markers `(*)`/`(**)` glued to the name, Duration in business days, ragged trailing empty fields.

## 4. Quirks
- Index/correction is free text (`DI + 1,6%`): spread must be parsed.
- The reference date does not appear in the first lines of the file (only in the file name) *(not verified for the whole file)*.
- Old layout (2013–2019) used `DBaammdd.TXT` / `dbAAMMDD.txt` under `/merc_sec_debentures/arqs/` (Wayback CDX).

## 5. Identity fields
`Código` = debenture ticker (B3/Cetip, e.g. AALM12); no ISIN/CNPJ in the file.

## 6. Ephemerality
**EPHEMERAL (6 business days).** Archive daily (178 KB txt). Internet Archive CDX: old path `/merc_sec_debentures/arqs/` lists 15 distinct daily txt dates (2013-03-20..2019-04-01) and 7 xls dates (2013-07-12..2018-02-06) — sparse, content not verified (replay blocked, HTTP 429); new path lists 3 URLs, all 404 captures. Full history = ANBIMA Feed (paid) or ANBIMA Data (token).

## 6b. History routes probed (2026-11-08): none public
- The form (`default.asp`, POST `Dt_Ref`) ignores the date: past dates (2019-05-10, 2026-01-02, 2026-10-20) return the same 12,674-byte page; its script only accepts the last 5 business days. Files: `db261106` and `db261029` 200 (178 KB); `db261020`, 261001, 260630, 260102, 251230, 241230, 230102, 190402, 181228 and the old path `/merc_sec_debentures/arqs/db190401.txt`, `DB130320.TXT` all 404.
- ANBIMA Data (`data.anbima.com.br/debentures/<ticker>/precos`) is a SPA over `data-api.prd.anbima.com.br` (404 without a token) whose search actions carry reCAPTCHA and an SSO login; `api.anbima.com.br/feed/...` answers 401 (client_id). Recorded and stopped: no login, no CAPTCHA.
- Substitutes already archived: B3 `Trade` per trade since 2023-03 (b3_fixed_income) and SND `precos`/`PU Histórico` (snd_pu_historico).

## 7. Open questions
- Where the reference date sits in the file; extra fields in xls; SND/B3 as free credit-price history.

## 8. Parsed (staging, `ingest/anbima_parsers.py`, 2026-11-07)
`debenture_rate`, partition `ref_date=` taken from the manifest (the file carries no date; settles open question §7). 15 `@` fields: `--` and `N/D` become null; `Nome` is split from its `(*)`/`(**)` marks; `Índice/Correção` is read into `indexer` (DI, IPCA, IGP-M, PRE) + `spread_pct` or `percent_of_di` (all 5 patterns seen: `DI + n%`, `IPCA + n%`, `PREFIXADO n%`, `n% do DI`, `IGP-M`; any other text raises). The last field is a date (maturity of the reference NTN-B). `% Reune` unit/meaning is not documented in the file (kept as published). 1,270-1,275 debentures a day; reparse 7,631 rows (6 days), 0 quarantined.
