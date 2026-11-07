# b3_company_events - B3: listed-companies site backend (proventos, eventos em ativos)

**Tier:** U. **Recon date:** 2026-11-07. **Fixture:** `tests/fixtures/b3_company_events/` (raw responses for ITUB, SLCE, RADL, EGIE, GRND, AZZA, BHIA, CRFB, JBSS, JBS-old; README + SHA256SUMS there).

Every statement below was measured on the recon date against a real response unless marked *(not verified)*.

## 1. Access
- Base `https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/CompanyCall/<Endpoint>/<param>`; `<param>` = standard base64 (with `=` padding; unpadded gives 200 with an empty body) of compact JSON. GET, no auth, no cookies. Plain curl UA and a Chrome UA both worked (200). No rate limiting seen at 1 req/s (about 150 requests).
- Wrong or unknown filters return **200 with empty body or empty `results`**, never an error. Unknown endpoint names return 404 (`GetListedStockDividends`, `GetListedSubscriptions` do not exist).
- **`"language":"pt-br"` is mandatory for a stable format.** With `en-us` the same fields come back US-formatted (`06/15/2007`, `2,926,680,320.30`, `0.86051967000`). Always send pt-br.
- Param keys are case-sensitive; order is irrelevant. `pageSize` works up to at least 120; 200 or more returns an empty page with null totals (the limit is between 121 and 199, not pinned down).

## 2. Endpoints and parameters
| endpoint | params that work | returns |
|---|---|---|
| `GetInitialCompanies` | `language, pageNumber(1..), pageSize, company` (name substring, optional; `segment` also filters) | paged list of 3550 issuers (30 pages x 120): `codeCVM, issuingCompany` (4-letter root, e.g. ITUB), `companyName, tradingName, cnpj` (digits, leading zeros dropped), `marketIndicator, typeBDR, dateListing` (`31/12/9999` = none), `status` (all `A`), `segment, segmentEng, type, market`. Delisted issuers (CRFB, VIIA, ARZZ) are **absent**. |
| `GetDetail` | `language, codeCVM` (string or int). `issuingCompany` returns an empty body. | one object: `issuingCompany, companyName, tradingName, cnpj, industryClassification(+Eng), activity, website, hasQuotation, status, marketIndicator, market, institutionCommon/Preferred, code` (main ticker), `codeCVM, lastDate` (`dd/mm/yyyy hh:mm:ss`, refresh time), `otherCodes[{code,isin}]` (current tickers only), `hasEmissions, hasBDR, typeBDR, dateQuotation`. `{}` for delisted CRFB. |
| `GetListedSupplementCompany` | `language, issuingCompany` (works also for delisted CRFB) | one-element array: share counts (`numberCommonShares`, `numberPreferredShares`, `totalNumberShares`, dotted thousands), `stockCapital`, `quotedPerSharSince, roundLot, tradingName` (padded with trailing spaces), `code, codeCVM, segment`, plus three arrays below. |
| `GetListedCashDividends` | `language, pageNumber, pageSize, tradingName` (exact; trailing spaces matter: the space-padded value from Supplement returned 0 rows for `JBS N.V.`). `issuingCompany`, `codeCVM`, or no filter all give 0 rows. | `{page:{pageNumber,pageSize,totalRecords,totalPages},results:[...]}`, newest first. |

`tradingName` is the only key of the cash endpoint, and it **changes with renames**: JBS S.A. rows live under `JBS` (10 rows, 2008-2019), JBS N.V. under `JBS N.V.` (0 rows; its 2026 BDR dividend is only in Supplement). The key must be resolved per period from the cadastro, not from the ticker.

## 3. Layout (dates `dd/mm/yyyy`; decimals with comma; numbers as strings)
**`GetListedCashDividends.results[]`** (full history; 22-960 rows per issuer measured):
`typeStock` (ON, PN, PNA/B/E, UNT), `dateApproval` (null on 90 of 960 ITUB rows, the oldest), `valueCash` (per share, up to 10 decimals), `ratio` and `quotedPerShares` (`1`, or `1000` when the price was quoted per 1000 shares: ITUB 258 rows, EGIE 33), `corporateAction` (DIVIDENDO, JRS CAP PROPRIO, RENDIMENTO), `lastDatePriorEx` (**data-com**, last date with the right; the ex-date is the next trading day, *(not verified here)*), `dateClosingPricePriorExDate`, `closingPricePriorExDate`, `corporateActionPrice` (valueCash / closing price x 100, a yield in percent), `lastDateTimePriorEx` (ISO `2026-10-30T00:00:00`). **No ISIN, no payment date, no `relatedTo`, no gross/net flag.**
**Supplement `cashDividends[]`**: `assetIssued, isinCode` (ISIN of the class), `paymentDate` (`31/12/9999` = not yet set; EGIE example), `rate` (per share), `relatedTo` (`Mensal/2026`, `Anual/2025`, `3º Trimestre/2025`, `Complementar/2025`), `approvedOn`, `label` (DIVIDENDO, JRS CAP PROPRIO), `lastDatePrior` (data-com), `remarks`. Only a **recent window**: ITUB 32 rows, approved 2024-12-19 to 2026-05-28; SLCE 2 rows.
**Supplement `stockDividends[]`**: `assetIssued, isinCode, factor, approvedOn, label, lastDatePrior` (data-com), `remarks`. Full history (ITUB back to 2011). **No ex-date, no payment date.** Labels seen: BONIFICACAO, DESDOBRAMENTO, GRUPAMENTO, CIS RED CAP, INCORPORACAO.
**Supplement `subscriptions[]`** (JBSS only, 2011): `percentage, priceUnit, tradingPeriod` (`06/06/2011 a 28/06/2011`), `subscriptionDate, approvedOn, label` SUBSCRICAO, `lastDatePrior`.

**Factor semantics (checked against known events, see golden_events.md):**
- BONIFICACAO: **percent of new shares** (`3,0` = 3 %, i.e. 103:100; `12,5` = 9:8; `2,0` = 51:50; `40,0` = 3.5:2.5).
- DESDOBRAMENTO: **percent increase**: RADL 2020 `400` = 1:5, SLCE 2023 `100` = 1:2, GRND 2018 `200` = 1:3 *(split ratios from memory, not checked against filings)*.
- GRUPAMENTO: **a fraction, not a percent**: BHIA `0,04` = 25:1; ITUB 2011 `0,01` = 100:1.
- The unit differs per label: the factor can never be read without the label.
- CIS RED CAP (ITUB 2021, factor 100) and INCORPORACAO (JBSS 2025, factor 50): semantics *(not verified)*.

Sample (verbatim): `{"assetIssued":"BRITUBACNOR4","factor":"3,00000000000","approvedOn":"18/12/2025","isinCode":"BRITUBACNOR4","label":"BONIFICACAO","lastDatePrior":"23/12/2025","remarks":""}`; `{"typeStock":"ON","dateApproval":"09/12/2025","valueCash":"0,018182","ratio":"1","corporateAction":"JRS CAP PROPRIO","lastDatePriorEx":"30/10/2026","dateClosingPricePriorExDate":"30/10/2026","closingPricePriorExDate":"43,06","quotedPerShares":"1","corporateActionPrice":"0,042225","lastDateTimePriorEx":"2026-10-30T00:00:00"}`.

## 4. Quirks
- **History depth**: cash series back to **1995-12-28** (ITUB), 1997 (RADL, BHIA), 2002 (EGIE), 2005 (GRND), 2008 (SLCE), 2011 (AZZA, since the Arezzo IPO), 2018 (CRFB: everything since its 2017 listing). Stock events back to 2011 for ITUB. JBS S.A.: 2008-2019 only; later dividends are missing under the `JBS` key *(possible gap, not verified)*.
- **Installments**: one declaration can appear as several rows with the same `dateApproval` and `lastDatePriorEx` and even an identical `valueCash` (GRND 2025-12-24: four rows 0,443380332 / 0,221690166 / 0,221690166 / 0,199503977, data-com 26/12/2025, paid 14/01, 18/03, 10/06, 09/09/2026 per Supplement). A dedupe on (date, value) would drop a real installment. The paged endpoint cannot tell them apart; only Supplement carries `paymentDate`.
- Older `valueCash` is not restated for later splits or bonuses (ITUB `ratio` 1000 rows).
- Mergers, ticker changes and delistings are **not events here**: ARZZ->AZZA keeps `codeCVM 22349` and a continuous dividend history; VIIA->BHIA keeps `codeCVM 6505` (history from 1997, last cash 2018-04-26); CRFB has empty event arrays; only the JBSS migration appears (INCORPORACAO).
- Supplement `tradingName` is space-padded to 12 characters; `cnpj` loses leading zeros; the ISIN class suffix identifies ON/PN.
- Encoding is UTF-8.

## 5. Identity fields
`codeCVM` (CVM_CODE, matches the cadastro), `issuingCompany` (ticker root), `cnpj`, `isinCode`/`assetIssued` (ISIN), `tradingName` (join key of the cash endpoint; unstable).

## 6. Ephemerality
The paged cash history and the stock events are persistent as served. Supplement cash and Detail's `lastDate` are a rolling window and **current state only** (a payment date of `31/12/9999` is overwritten later). Archive Supplement per issuer at every refresh: it is the only source of payment dates, and no announcement timestamp is provided, so the knowledge time is the fetch time. Delisted issuers disappear from GetInitialCompanies, so keep the issuer list.

## 7. Open questions
- Exact `pageSize` ceiling (120 ok, 200 not).
- Whether the ex-date is always the next trading day after `lastDatePrior` (check against COTAHIST).
- Why JBS cash rows stop in 2019.
- Semantics of the CIS RED CAP and INCORPORACAO factors.
