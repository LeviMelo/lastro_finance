# b3_settlement_prices — B3: ajustes do pregão (via BDI)

**Tier:** P. **Recon date:** 2026-11-07 (partial; stopped early). **Fixture:** `tests/fixtures/b3_settlement_prices/` (BDI JSON, see README).

## 1. Access
- Old page `www2.bmf.com.br/.../lum-ajustes-do-pregao-ptBR.asp`: POST `dData1=06/11/2026` → **301** to b3.com.br "Boletim Diário do Mercado"; GET without params → 301; GET with `?dData1=` → 200 with empty body. Cloudflare in front, browser UA used, TLS fine. B3 notice in BDI config.js: the "Dados públicos de produtos listados e de balcão" and "Cotações" pages were deactivated (31/03/2026); their data is in the BDI since 15/12/2025 (Comunicado Externo 01/2026-VTEC).
- Replacement: BDI app `https://arquivos.b3.com.br/bdi/` (JSON backend, no auth, no token: `useToken:false`).
  - Catalog: GET `/bdi/table/classifications` (`/bdi/table/all` returns `{}`).
  - Data: POST `/bdi/table/<TableName>/<YYYY-MM-DD>/<YYYY-MM-DD>/<page>/<take>[?filter=<base64(ticker)>]`, body `{}`, `Content-Type: application/json`.
  - Filter is an exact ticker match (case-insensitive): `DI1F27` → 1 row; `DI1` → 0 rows.
  - Latest date: GET `/bdi/table/workday` → `"2026-11-06T00:00:00"`. Available dates: GET `/bdi/table/workdays?date=…&limitDate=D-21`.
- Settlements are in table **ConsolidatedTradesDerivatives** (id 672, "Negócios consolidados do pregão", SLA 21:00). 2026-11-06 had pageCount 1520 at take=5 (≈7.6k instruments).

## 2. Datasets
| dataset_id | granularity | history depth | cadence | URL pattern |
|---|---|---|---|---|
| ConsolidatedTradesDerivatives | instrument × day | **21 business days** (`limitDate: D-21`; 2026-10-07 served, 2026-10-06 and older return empty `values`) | daily, published evening D0 (lastUpdateDate 2026-11-06T23:01) | as above |
| OpenPositionsEquities, AnalyticalFramework2 (open interest) | — | D-21 | daily | *(not verified: not fetched)* |
- `www.b3.com.br/pesquisapregao/download?filelist=PR261106.zip,` → 200, 11 MB zip-in-zip with 4 × BVBG.086.01 XML (~130 MB each). Likely contains settlement and open interest; **content and history depth not verified**.

## 3. Layout (ConsolidatedTradesDerivatives, from `columns` in the response)
`RptDt` (date, ISO `2026-11-06T00:00:00`), `TckrSymb`, `ISIN`, `SgmtNm`, `Mkt`, `OpenPric`, `MinPric`, `MaxPric`, `TradAvrgPric`, `LastPric`, `Osc`, `AdjstdQt` (Ajuste), `AdjstdQtTax` (Ajuste de referência; for DI1 = rate), `PrvsAdjstdQt` (ajuste anterior), `RefPric`, `VartnPts`, `AdjstdValCtrct` (R$/contrato), `BestBidPric`, `BestAskPric`, `TradQty`, `FinInstrmQty`, `NtlFinVol`. Rows are positional arrays in `table.values`.
```
["2026-11-06T00:00:00","DI1F27","BRBMEFD1I4Z0","FINANCIAL","FUTURE",13.66,13.658,13.665,13.662,13.662,0.01,98087.22,13.664,98087.69,null,-0.47,-0.47,13.662,13.664,14025,522599,51260388907.12]
```

## 4. Quirks
- JSON UTF-8 with `\u00XX` escapes; numbers are JSON numbers (dot decimal). Nulls for untraded fields. DI1 `AdjstdQt` is PU, `AdjstdQtTax` the rate (% a.a.).
- Holidays absent from `workdays` (2026-11-02, 2026-10-12).

## 5. Identity fields
TckrSymb (TICKER), ISIN.

## 6. Ephemerality
**Rolling 21-business-day window: archive daily** or history is lost (unless BVBG.086 files in pesquisapregao serve older dates — not verified).

## 7. Open questions
- BVBG.086.01 field list, and how far back `pesquisapregao` serves PR files.
- Open interest tables in BDI (not fetched). Page size limit of `take`.
