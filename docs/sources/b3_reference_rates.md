# b3_reference_rates — B3: taxas referenciais (DI × pré, DI × IPCA, ...)

**Tier:** P. **Recon date:** 2026-11-07. **Fixture:** `tests/fixtures/b3_reference_rates/` (README has requests and sha256).

## 1. Access
- Old `https://www2.bmf.com.br/pages/portal/bmfbovespa/boletim1/TxRef1.asp?...` → 404 (pass 1: with and without UA; http:// 520; host root 403): decommissioned.
- Current B3 page `https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/consultas/mercado-de-derivativos/precos-referenciais/taxas-referenciais-bm-fbovespa/` iframes `https://sistemaswebb3-derivativos.b3.com.br/referenceRatesPage/all?language=pt-br` (Angular SPA). Backend (read from `main-*.js`): `https://sistemaswebb3-derivativos.b3.com.br/referenceRatesProxy/Search/<Endpoint>/<base64(json)>`, GET, browser UA, no auth.
  - `GetProducts` `{"language":"pt-br"}` → 22 ids: ACC APR DCO DOC DOL EUC DIM DIC **PRE** TR DPL INP BRP LIB PDN PTX EUR JPY SLP SDE TFP TP (descriptions: PRE "DI x pré", DIC "DI x IPCA", DIM "DI x IGP-M", TR "DI x TR", DOL "DI x dólar", DOC "Cupom limpo", ACC "Ajuste cupom", APR "Ajuste pré", DPL "Cupom limpo de IPCA", …).
  - `GetDate` `{"language":"pt-br","id":"PRE"}` → the 20 latest dates only (2026-11-06 … 2026-10-08); this is a UI list, **the files are served for more dates** (below).
  - `GetList` `{"language":"pt-br","id":"PRE","pageNumber":1,"pageSize":5,"date":"2026-11-06"}` → `{"page":{totalRecords:282,…},"results":[{"code":"PRE","curve":"T1","description":"DI x pré","day252":1,"day360":3,"rate":"13,65"},…]}`.
  - `GetDownloadFile` `{"language":"pt-br","date":"YYYY-MM-DD","id":"PRE"}` → **base64 text of a CSV** (Latin-1, CRLF): `Descrição da Taxa;Dias Úteis;Dias Corridos;Preço/Taxa`. Empty body (HTTP 200) for a date not served.
- **Long-history route: pesquisapregao `TS{YYMMDD}.ex_`** ("Mercado de Derivativos – Taxas de Mercado para Swaps"): `GET https://www.b3.com.br/pesquisapregao/download?filelist=TS261106.ex_,` (see b3_settlement_prices.md for the mechanics). It is a zip of a PKWARE **PKSFX self-extracting EXE** (MZ header; the ZIP starts at byte 86,036; do NOT execute it, open it as a zip: Python `zipfile` accepts the prefix) holding `TaxaSwap.txt`.
- Not curves: BDI tables `EconomicIndicators` (RT* indicators), `DIover` (daily DI over, see b3_instruments.md), `HistoricalExchange` — no term structures in the BDI catalog.

## 2. Datasets
| dataset_id | granularity | history depth (measured) | cadence | URL |
|---|---|---|---|---|
| referenceRates `GetDownloadFile` (19 products probed non-empty, PDN empty on every date tried; GetDate empty for TR/TP/PDN though the files exist) | curve × day × vertex (282 vertices on 2026-11-06) | **2026-10-05 → today** (10-05 and 10-06 present, 10-02, 10-01 and 09-30 …2023-01-03 empty; same for the 19 products with data tried: ACC…EUR, SDE, TFP, TP) | daily, available for 2026-11-06 on 11-07 ~09:00 UTC | referenceRatesProxy/Search/GetDownloadFile |
| **TS (TaxaSwap.txt)** | all curves × day × vertex (31,482 lines, 97 curve names on 2026-11-06) | **2000-01-14 → today** (2000-01-13, 01-11, 01-10, 01-03, 1999-12-01, 1999-10-01, 1999-06-01 absent; every probe date 2000-01-17 … 2026 present: 2000-11-06, 2001-11-06, 2002…2025-11-06, 2018-01-02, 2010-01-04) | daily | `filelist=TS<YYMMDD>.ex_,` (zip 330 KB in 2026, 19 KB in 2000) |
The curves in the CSV and in TS are the same numbers: DIC 282/282 vertices identical on 2026-11-06 (du, dc, rate); **PRE in the web CSV is rounded to 2 decimals while TS keeps 3** (max difference 0.005 pp). TS is therefore both the longer and the more precise route. Gaps in TS: dates between probes not individually checked *(not verified: holidays/missing days)*.

## 3. Layout
**CSV** (`GetDownloadFile`): `;` separated, CRLF, decimal comma; rows e.g. `DI x pré;1;3;13,65` (du=1, dc=3 on 2026-11-06). 282 rows (PRE, DIC) / vertex du from 1 to 8,459 (PRE) / dc up to 12,337.
**TaxaSwap.txt** fixed width, CRLF, ISO-8859-1, no header (inferred from data and cross-checked against the CSV; the official `Eletro.xls` "layout" in `Layout … Taxas de Mercado para Swaps-atual.zip` on the layout page documents the OTC trades file (sheet "Negócios realizados no mercado de balcão"), **not** TaxaSwap):
| pos (1-based) | content (2026 format, 72 chars) |
|---|---|
| 1-6 | sequence |
| 7-9 / 10-11 | `001` / `01` |
| 12-19 | date `AAAAMMDD` |
| 20-21 | `T1` |
| 22-24 | curve code (PRE, DIC, DOL, TR, INP, …; 3 chars, space padded) |
| 27-41 | curve description (15 chars) |
| 42-46 | calendar days (`Dias Corridos`) |
| 47-51 | business days (`Dias Úteis`) |
| 52 | sign |
| 53-66 | value, integer with 7 implied decimals (`00000136500000` = 13.65) |
| 67 | vertex type `F`/`M` (*meaning not verified*) |
| 68-72 | business days again (or calendar days; equal to the vertex in the sample) |
```
0154080010120261106T1PRE  DIxPRE         0000300001+00000136500000F00001
0069480010120261106T1DIC  DI X IPCA      0000300001+00000136500000F00001
```
Era differences (measured): 2000-01-14: 65 chars, 12-digit value, no type letter, 12 curves, 41 PRE vertices (`0000300001+000183200000 `); 2010-01-04: 72 chars, 54 curves, 173 PRE vertices; 2018-01-02: 103 curves, 318 PRE vertices; 2026-11-06: 97 curve names, 282 PRE vertices. Curve code set changes over time (e.g. `AN`/`ANBIDxDI1` only in 2000). A parser must key on position per era.

## 4. Quirks
- The curve vertex set changes by day (282 rows on 2026-11-06, 283 on 2026-10-08, 278 on 2026-10-05, PRE): do not assume fixed vertices.
- Rates: % a.a. (252 for PRE, DIC rates are the real coupon rate; `Dias Úteis` = business days to the vertex).
- ex_ is an executable container: treat as untrusted, parse statically.

## 5. Identity fields
Curve code (PRE, DIC, …) is the series key; no instrument identity.

## 6. Ephemerality
The web CSV is a ~23-business-day window → **archive daily**, but **TS gives full history from 2000-01-14**: backfill TS (≈ 6,900 requests, ≈ 3-6 GB zipped) and archive each day. Internet Archive: `www2.bmf.com.br/…/TxRef1.asp*` has 69 captures 2016-04-20 → 2025-06-24 (2016 10, 2017 8, 2018 11, 2019 2, 2020 2, 2022 21, 2023 5, 2024 8, 2025 2; 68 distinct digests) — sporadic, a poor substitute; `referenceRatesProxy/*` has 0 captures.

## 7. Open questions
- Exact TaxaSwap field semantics for per-curve codes, vertex type F/M and the last 5-digit field; the official layout of TaxaSwap.txt was not found (only the unrelated `Eletro.xls`).
- Whether TS is complete day by day (holes) and whether older files are ever rewritten.
- Which TS curve codes map to ANBIMA/B3 "pre-fixados" used by the valuation engine (PRE = "DIxPRE", DIC = "DI X IPCA" by value match).
