# b3_company_events fixtures

Raw, byte-exact responses (UTF-8 JSON, no re-encoding) from the B3 listed-companies backend,
`https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/CompanyCall/<Endpoint>/<base64(JSON params)>`.
Fetched 2026-11-07 (UTC), language `pt-br`, browser User-Agent, 1 request/s. Checksums: `SHA256SUMS`.

| file | request (params JSON, then base64) |
|---|---|
| `<ISS>_supp.json` | `GetListedSupplementCompany` `{"language":"pt-br","issuingCompany":"<ISS>"}`; ISS = ITUB SLCE RADL EGIE GRND AZZA BHIA CRFB JBSS |
| `<ISS>_detail.json` | `GetDetail` `{"language":"pt-br","codeCVM":<n>}` (CRFB: `{}`, empty for a delisted issuer) |
| `<ISS>_cash_pN.json` | `GetListedCashDividends` `{"language":"pt-br","pageNumber":N,"pageSize":120,"tradingName":"<name>"}`; names: ITAUUNIBANCO, SLC AGRICOLA, RAIADROGASIL, ENGIE BRASIL, GRENDENE, AZZAS 2154, CASAS BAHIA, CARREFOUR BR, JBS N.V. (0 rows) |
| `JBSold_cash_p1.json` | same, `tradingName` = `JBS` (the pre-2025 JBS S.A. name) |
| `GetInitialCompanies_p1_size120.json` | `GetInitialCompanies` `{"language":"pt-br","pageNumber":1,"pageSize":120}` (page 1 of 30) |
| `GetInitialCompanies_company-ITAU.json` | `GetInitialCompanies` `{"language":"pt-br","pageNumber":1,"pageSize":120,"company":"ITAU"}` |

All pages of each cash series are kept (complete history for the 8 issuers). Cut: none; files are whole responses.
