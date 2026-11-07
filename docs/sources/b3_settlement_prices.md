# b3_settlement_prices — B3: ajustes do pregão (settlement prices) and open interest

**Tier:** P. **Recon date:** 2026-11-07 (pass 1 BDI; pass 2 history routes). **Fixture:** `tests/fixtures/b3_settlement_prices/` (BDI JSON from pass 1; BVBG.086 XML excerpts 2026 and 2018; TradeInformationConsolidatedFile excerpt; README has sha256).

## 1. Access
- Old page `www2.bmf.com.br/.../lum-ajustes-do-pregao-ptBR.asp` 301-redirects to the BDI; B3 notice (config.js, 31/03/2026): the "Dados públicos de produtos listados e de balcão" and "Cotações" pages were deactivated, their data is in the BDI since 15/12/2025 (Comunicado Externo 01/2026-VTEC).
- **Route A (long history): "Pesquisa por pregão"** — `GET https://www.b3.com.br/pesquisapregao/download?filelist=<CODE><YYMMDD>.<zip|ex_>,` (trailing comma; several files may be comma-separated). No auth, Cloudflare, browser UA used. The response is `application/octet-stream`, `filename="pesquisa-pregao.zip"`, **HTTP Range is ignored (full body returned)**, no Content-Length. Missing dates return HTTP 200 with a 22-byte empty zip (`PK\x05\x06`), so "absent" = body of 22 bytes. The page (`…/historico/boletins-diarios/pesquisa-por-pregao/pesquisa-por-pregao/`) builds the same URL from 39 checkbox values (`value="PR{YYMMDD}.zip"`); layouts at `…/pesquisa-por-pregao/layout-dos-arquivos/`, descriptions at `…/descricao-dos-arquivos/`.
- **Route B (17 months): file `TradeInformationConsolidatedFile`** at arquivos.b3.com.br (two-step token download, see b3_instruments.md). CSV, one row per instrument, includes `AdjstdQt`/`AdjstdQtTax` (settlement PU / rate) but **no open interest**.
- **Route D (4.7 years, PDF): daily Boletim Diário PDF** `https://arquivos.b3.com.br/bdi/download/bdi/<date>/BDI_00_<YYYYMMDD>.pdf`, served 2022-03-01 → yesterday (b3_instruments.md): contains settlement per instrument (DI1F27 on 2026-11-05: `98.037,91`) and open positions (`8.219.135`, equal to the PR XML `OpnIntrst`). Useful only as a cross-check/backfill for 2022-03 → 2025-06 if PR were unavailable; PR covers it better.
- **Route C (21 business days): BDI JSON** `POST https://arquivos.b3.com.br/bdi/table/<Table>/<d>/<d>/<page>/<take>[?filter=<base64 ticker>]`, body `{}`; catalog `GET /bdi/table/classifications`; latest day `GET /bdi/table/workday`; table `ConsolidatedTradesDerivatives` (id 672). Window D-21: 2026-10-07 served, 2026-10-06 and older empty. Open interest tables `OpenPositionsEquities` (670), `AnalyticalFramework2` (692): same D-21 (open-interest content not fetched).

## 2. Datasets
| dataset_id | granularity | history depth (measured) | cadence | URL pattern |
|---|---|---|---|---|
| **PR (BVBG.086.01 Price Report)** | message per instrument × day, ≈ 57k per XML | **2018-01-02 → today** (2017-12-29 and every date before it absent, incl. 2017-06-01, 2017-01-03, 2016-06-01, 2012-06-01) | daily, 4 snapshots/day (below) | `filelist=PR<YYMMDD>.zip,` |
| TradeInformationConsolidatedFile | instrument × day | 2025-06-10 → today | daily | see b3_instruments.md |
| BDI ConsolidatedTradesDerivatives | instrument × day | 2026-10-07 → today | daily | Route C |
- 2026-11-06 zip: 11,079,662 bytes → one inner zip → **4 XML** of 128–132 MB (`BVBG.086.01_BV0003282026110603280000018394…xml`, creation times in `BizGrpDtls/CreDtAndTm`: 18:39:38, 19:16:45, 20:10:15, 20:40:26) with 57,131 / 57,111 / 57,773 / 55,934 `PricRpt`. They are **successive snapshots of the same day**: 95–99% of elements are byte-identical across files, union = 57,717 distinct tickers (58,368 distinct elements). In 2018-01-02 (1.25 MB zip, 3 XML of 21 MB) the **first snapshot lacks `AdjstdQt` for INDG18; the 2nd and 3rd have it** (DI1F19, DOLG18 have it in all). Rule for the loader: archive the whole zip; merge all snapshots keyed by (`TradDt`, `TckrSymb`), preferring the latest element that carries `AdjstdQt`. Older sizes: 2025-11-06 7.3 MB zip (3 XML of 113 MB), 2024-11-06 5.7 MB (3 XML of 90 MB).
- Sizes imply ≈ 3–11 MB/day compressed: 2018→2026 ≈ 2,000 days ≈ 10–15 GB.

## 3. Layout (BVBG.086.01, read from the 2026-11-06 and 2018-01-02 files; namespace `urn:bvmf.052.01.xsd` envelope, messages `urn:bvmf.217.01.xsd`)
Envelope `BizFileHdr/Xchg/BizGrp` repeated per message; each message `Document/PricRpt`. Streaming parse (iterparse + `clear()` or bytes regex on `<PricRpt>…</PricRpt>`); never load a 130 MB XML into memory. Counts in the 2026-11-06 files (227,949 `PricRpt` over 4 files): `TradDt/Dt` 2026-11-06 (227,901) and 2026-11-09 (48); `OpnIntrst` in 178,653; `AdjstdQt` 2,494; `AdjstdQtTax` 1,222; `PrvsAdjstdQt` 2,688; `VartnPts` 2,494; `AdjstdValCtrct` 2,494; `FrstPric` 65,190; `NtlFinVol` 65,232.
Fields of `PricRpt`: `TradDt/Dt`; `SctyId/TckrSymb`; `FinInstrmId/OthrId/Id` (B3 numeric instrument id, e.g. 409606 for DI1F27; `Tp/Prtry` 8); `TradDtls/TradQty`; `FinInstrmAttrbts/`: `MktDataStrmId`, `NtlFinVol` (Ccy BRL), `IntlFinVol` (USD), **`OpnIntrst`**, `FinInstrmQty`, `BestBidPric`, `BestAskPric`, `FrstPric`, `MinPric`, `MaxPric`, `TradAvrgPric`, `LastPric`, `RglrTxsQty`, `RglrTraddCtrcts`, `NtlRglrVol`, `IntlRglrVol`, **`AdjstdQt`** (settlement price; for DI1 the PU), **`AdjstdQtTax`** (DI1: settlement rate % a.a.), `AdjstdQtStin` (F/U = final/undefined *meaning not documented here*), `PrvsAdjstdQt`, `PrvsAdjstdQtTax`, `PrvsAdjstdQtStin`, `OscnPctg`, `VartnPts`, `AdjstdValCtrct` (R$/contract adjustment), `MaxTradLmt`, `MinTradLmt`, `EqvtVal`, `NonRglr*`.
**Confirmed contents (2026-11-06):** DI1F27 `AdjstdQt` 98087.22 (PU), `AdjstdQtTax` 13.664, `OpnIntrst` 8,219,135; DOLZ26 `AdjstdQt` 5523.964, `OpnIntrst` 833,299; INDZ26 `AdjstdQt` 170484, `OpnIntrst` 184,688; WINZ26 `OpnIntrst` 1,275,337. **2018-01-02:** DI1F19 `AdjstdQt` 93677.51, `AdjstdQtTax` 6.805, `OpnIntrst` 2,567,228; DOLG18 3270.387 / 541,838; INDG18 78313 / 369,265. The values equal the BDI/TradeInformation rows of the same day (DI1F27: 98087.22 / 13.664 in all three).
```
<PricRpt><TradDt><Dt>2026-11-06</Dt></TradDt><SctyId><TckrSymb>DI1F27</TckrSymb></SctyId> … <OpnIntrst>8219135</OpnIntrst> … <AdjstdQt Ccy="BRL">98087.22</AdjstdQt><AdjstdQtTax Ccy="BRL">13.664</AdjstdQtTax> …
```
(BDI JSON layout from pass 1: `RptDt, TckrSymb, ISIN, SgmtNm, Mkt, OpenPric, MinPric, MaxPric, TradAvrgPric, LastPric, Osc, AdjstdQt, AdjstdQtTax, PrvsAdjstdQt, RefPric, VartnPts, AdjstdValCtrct, BestBidPric, BestAskPric, TradQty, FinInstrmQty, NtlFinVol`; TradeInformationConsolidatedFile header: `RptDt;TckrSymb;ISIN;SgmtNm;MinPric;MaxPric;TradAvrgPric;LastPric;OscnPctg;AdjstdQt;AdjstdQtTax;RefPric;TradQty;FinInstrmQty;NtlFinVol`, decimal comma, row `2026-11-06;DI1F27;BRBMEFD1I4Z0;FINANCIAL;13,658;13,665;13,662;13,662;0,01;98087,22;13,664;;14025;522599;51260388907,12`.)

## 4. Quirks
- XML files begin with a UTF-8 BOM; decimals use `.`; each message carries its own `Ccy` attributes. A handful of messages are dated the next business day (2026-11-09, 48 in 2026-11-06; 2018-01-03, 18 in 2018-01-02): filter on `TradDt` = the requested day or keep it as is and key on `TradDt`.
- DI1 prices: rate in `AdjstdQtTax`, PU in `AdjstdQt`; the intraday `LastPric` of DI1 is a rate.
- The BDI JSON is UTF-8 with `\u00XX` escapes; holidays are absent from `workdays`.
- Non-trading days: HTTP 200 + 22-byte empty zip (weekends, holidays); an empty zip is NOT an error.

## 5. Identity fields
`TckrSymb` (TICKER), B3 numeric instrument id (`OthrId/Id`), ISIN only in the BDI/TradeInformation CSV.

## 6. Ephemerality
- PR files: **not ephemeral** (served back to 2018-01-02) → backfill 2018-01-02 → today (≈ 2,200 requests, ≈ 10–15 GB) and keep archiving daily (the 4 snapshots may be revised the same evening; fetch after ~21:00 BRT *(timing not measured)*).
- TradeInformation, BDI tables: window 2025-06-10 (17 months) / D-21: archive daily until PR backfill is done and checked; they provide an independent cross-check of the PR XML (invariant 7).
- Before 2018-01-02: no B3 route found (PR absent). COTAHIST derivatives (b3_cotahist.md) hold prices/volumes, not settlements/open interest *(not verified for DI1)*.

## 7. Other pesquisapregao file families (same URL pattern; 39 codes = the page's checkbox set)
Probe dates (non-empty body = served): 2026-11-06, 2025-11-06, 2024-11-06, 2023-11-06, 2022-11-07, 2021-11-05, 2020-11-06, 2019-11-07, 2018-11-08, 2018-01-02, 2017-11-06, 2016-11-07, 2015-11-06, 2013-11-07, 2011-11-07, 2009-11-06, and for the old families also 2008-11-06 … 1997-11-06. "Oldest" is the oldest probe date with data unless marked *(bisected)*; days between probes were not checked, and several families have missing days (e.g. IN absent on 2018-11-08 but present on 2018-01-02 and 2019-11-07).
| code | content | served (oldest … newest probe) |
|---|---|---|
| **PR** | BVBG.086.01 Price Report (trades, settlement, open interest) | **2018-01-02** *(bisected; 2017-12-27/28/29 and 2017-06-01 absent)* … today |
| SPRE / SPRD | BVBG.186/187 simplified price report, equities / derivatives | 2022-11-07 … today (absent 2021-11-05) |
| IR | BVBG.087.01 index report (levels, IOPV) | 2016-11-07 … today (absent 2015-11-06) |
| IN | BVBG.028.02 instrument registry (tradable and collateral instruments) | 2018-01-02 … today (absent 2017-11-06) |
| II | BVBG.029.02 indicator instruments | 2018-01-02 … 2026-11-06 |
| SecurityList | tradable securities list | 2024-11-06 … today (absent 2023-11-06) |
| **TS** (.ex_) | swap market rates = all B3 curves (see b3_reference_rates.md) | **2000-01-14** *(bisected)* … today |
| CT / CV | FX market: rates practised / net settled volume | ≈ 2002-04-22 *(partial bisect: 2002-04-17 absent, 2002-04-22 present; 2001-11-06 absent)* … today |
| ID (.ex_) | derivatives economic and agricultural indicators, final | ≈ 1999-09-30 *(partial bisect: 1999-09-20 absent, 1999-09-30 present)* … today |
| BE (.ex_) | OTC derivatives trades | ≤ 1999-11-08 … 2025-11-06 (absent 2026-11-06) |
| MM (.ex_) | swap FX mark to market | 2000-11-06 … today (absent only on the 2015-11-06 probe) |
| RE (.ex_) / PE (.ex_) | option reference premium, derivatives / equities | RE 2005-11-07 … today; PE 2016-11-07 … today |
| IV / IS (.ex_) | ISIN lists of derivatives / swap contracts (page: discontinued) | 2004-11-05 … 2025-11-06 |
| IC (.ex_) | ISIN list for CPRs (discontinued) | 2011-11-07 … 2025-11-06 |
| PU (.ex_) | public securities reference prices | 2004-11-05 … today |
| RF (.ex_) | private fixed income | 2016-11-07 … today (absent 2018-01-02) |
| DI | daily unit fee cost | 2017-11-06 … today |
| FP / FR | primitive risk factors / risk formulas | FP 2020-11-06 … 2025-11-06; FR 2019-11-07 … 2025-11-06 |
| AI, LD, LA, MO, MP, MT, PG | instrument groups, liquidity limits, OTC/standard mappings, max theoretical margin, group parameters | each from 2018-01-02 (LA from 2022-11-07; MT till today, others till 2025-11-06) |
| CN / GL | margin scenarios for liquid assets, GTSLiNe weights | 2017-11-06 … 2025-11-06 |
| RV / PT (.ex_) | structured volatility operations / locked positions (PT: discontinued 15/12/2025 per page) | RV 2009-11-06 … 2022-11-07; PT 2009-11-06 … 2025-11-06 |
| LB | BACEN auction trades | 2016-11-07 … 2018-11-08 only |
| HF, UN, VA, TX | fee/HFT parameters, equities fees (BVBG.072.01) | only the 2018-01-02 probe was non-empty (TX also 2018-01-02 only) |

## 8. Open questions
- Exact oldest dates for the families marked "≥/not bisected" (only PR and, where given, others were bisected).
- Meaning of `AdjstdQtStin` (F/U) and of the four snapshots (are late snapshots corrections?). The layout PDF for BVBG.086.01 was not read.
- Time of day when the final snapshot is available; whether past-day files are ever rewritten.
- BDI open-interest table content (OpenPositionsEquities) vs `OpnIntrst` in PR: not compared.
