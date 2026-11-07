# b3_instruments — B3: Cadastro de Instrumentos (InstrumentsConsolidatedFile) and the BDI table catalog

**Tier:** P. **Recon date:** 2026-11-07. **Fixture:** `tests/fixtures/b3_instruments/` (excerpt of the 2026-11-06 CSV; README has sha256).

Every statement was measured on the recon date unless marked *(not verified)*.

## 1. Access
Two routes on `arquivos.b3.com.br`, no auth, no reCAPTCHA, browser User-Agent used (a non-browser UA was not tried). Cloudflare in front.
- **File route (long window).** `GET /api/download/requestname?fileName=InstrumentsConsolidatedFile&date=YYYY-MM-DD` returns JSON `{"redirectUrl":"~/download?token=…","token":"…"}`; then `GET /api/download/?token=<token>` returns the CSV (`Content-Disposition: attachment; size=20091058; filename=InstrumentsConsolidatedFile_20261106_1.csv`, `application/octet-stream`, chunked, no Content-Length). The same two calls are what the `/tabelas/` SPA does (`/tabelas/InstrumentsConsolidated/<date>?lang=pt` is only the HTML shell). Weekends return an empty body (no token); a date with no file returns a token but a 0-byte body.
- **JSON route (short window).** BDI: `POST /bdi/table/InstrumentsEquities|InstrumentsDerivatives/<d>/<d>/<page>/<take>`, body `{}` (see b3_settlement_prices.md). 2026-11-06 InstrumentsEquities = 81,098 rows; the response carries the column dictionary (`columns[].friendlyNamePt`). Window D-21 only (2026-10-07 served, 2026-10-06 empty) — **the BDI JSON is NOT the route to history.**
- **PDF route (longest on this host): the daily "Boletim Diário do Mercado" PDF**, `GET https://arquivos.b3.com.br/bdi/download/bdi/<YYYY-MM-DD>/BDI_00_<YYYYMMDD>.pdf` (URL built by the BDI app: `downloadUrl` + date + `BDI_00_…pdf`; English `_en-Us`). No token. `application/pdf`; 2026-11-05 = 32,353,796 bytes, 1,789 pages. **Served 2022-03-01 → yesterday** (2022-03-01, 2022-04-01 … 2026-11-05 return `%PDF`; 2022-02-28, -25, -21, -14, -07, 2022-01-04, -10, 2021-12-30 and 2021-06-01 … 2015-06-01 return HTTP 500; 2026-11-06, the latest day, returned 500 at ~08:30 UTC, not yet published). Content (measured on 2026-11-05 by text extraction, PyMuPDF): the BDI tables as text tables — DI over (p.4), consolidated equity trades (p.281), **composition of 31 index portfolios** (p.1036-1064: IBOVESPA, IGCX, IBRX50, IBXX, SMLL, MLCX, ICON, IMOB, IFNC, IDIV, IFIX, BDRX, … with theoretical quantity and weight), derivatives trades **with settlement** (p.1253: DI1F27 `98.037,91`, rate `13,6600`), **open positions** (p.1264: DI1F27 8.219.135, equal to `OpnIntrst` in the BVBG.086 XML), lending (p.1716-1788), economic indicators (p.1073). Per the BDI notices the instrument-registry tables are **not** in the PDF. Layout is multi-column text split across pages (values appear in column order, `-` = null): needs a table-aware parser; tier is P but extraction is fragile.
- Tried and dead: `/api/channels/public/InstrumentsConsolidated` 404; `/apinegocios/tickercsv/PETR4/<date>` 404 for every date incl. today; `/apinegocios/dates?type=N` empty.
- Other file names accepted by `requestname` (same flow, same window, measured): **`TradeInformationConsolidatedFile`** (trade summary of all instruments incl. DI1/DOL/IND settlement `AdjstdQt`/`AdjstdQtTax`, see b3_settlement_prices.md) and `TradeInformationConsolidatedAfterHoursFile`. ~35 other guessed names (open positions, lending, indices, BDI table name + `File`) return empty: no other file in this family found *(guesses, not exhaustive)*.

## 2. Datasets
| dataset_id | granularity | history depth | cadence | lag | URL pattern |
|---|---|---|---|---|---|
| InstrumentsConsolidatedFile | instrument × day, all segments (89,144 rows on 2026-11-06) | **2025-06-10 → today, 356 files**: 2025-06-09, -06 and every earlier date tried (2025-05-15, 03-03, 01-02, 2024-06-03, 2022-06-01) return empty. Business days with no file: 2025-06-19, 11-20, 12-25, 2026-01-01, 02-16, 02-17, 04-03, 04-21, 05-01, 06-04, 09-07, 10-12, 11-02 (all B3 holidays). 2025-12-24 (7 KB) and 2025-12-31 (756 B) are header-only/truncated. | daily | same evening (11-06 served on 11-07 ~08:30 UTC; line 1 `Status do Arquivo: Final`) | above |
| TradeInformationConsolidatedFile | instrument × day (81,664 rows) | 2025-06-10 → today (same cut-off; probed 06-09, 06-06 and 2025-01-02…2010-01-04 empty) | daily | same | same flow |
| BDI JSON tables | see catalog below | D-21 for most | daily | 21:00 SLA | `/bdi/table/<Name>/…` |
- Whether 2025-06-10 is a fixed start or a rolling ~17-month window is **not known** (one observation date). Re-measure the oldest date in a later session: if it stays 2025-06-10 the start is fixed.
- 2025-06-10 is a Tuesday; 2025-06-09 (Monday, not a holiday) is absent too, so the serving history starts there, not at a holiday gap.

## 3. Layout (InstrumentsConsolidatedFile; identical header on 2025-06-10, 2025-12-15, 2026-11-06)
Line 1 `Status do Arquivo: Final`; line 2 header; then `;`-separated rows, LF line ends, ISO-8859-1. 51 columns:
`RptDt;TckrSymb;Asst;AsstDesc;SgmtNm;MktNm;SctyCtgyNm;XprtnDt;XprtnCd;TradgStartDt;TradgEndDt;BaseCd;ConvsCritNm;MtrtyDtTrgtPt;ReqrdConvsInd;ISIN;CFICd;DlvryNtceStartDt;DlvryNtceEndDt;OptnTp;CtrctMltplr;AsstQtnQty;AllcnRndLot;TradgCcy;DlvryTpNm;WdrwlDays;WrkgDays;ClnrDays;RlvrBasePricNm;OpngFutrPosDay;SdTpCd1;UndrlygTckrSymb1;SdTpCd2;UndrlygTckrSymb2;PureGoldWght;ExrcPric;OptnStyle;ValTpNm;PrmUpfrntInd;OpngPosLmtDt;DstrbtnId;PricFctr;DaysToSttlm;SrsTpNm;PrtcnFlg;AutomtcExrcInd;SpcfctnCd;CrpnNm;CorpActnStartDt;CtdyTrtmntTpNm;MktCptlstn;CorpGovnLvlNm`
(The BDI JSON variant has 31 columns, a subset; `CrpnNm` = issuer name, `MktCptlstn` = capital social, `CorpGovnLvlNm` = listing segment e.g. `NIVEL 2`.)
```
2026-11-06;PETR4;PETR;PETR;CASH;EQUITY-CASH;SHARES;;;2026-08-24;9999-12-31;;;;;BRPETRACNPR6;EPNNPR;;;;;;1;BRL;;;;;;;;;;;;;;;;;230;1;2;;;;PN      N2;PETROLEO BRASILEIRO S.A. PETROBRAS;9999-12-31;FUNGIBLE;5446501379;NIVEL 2
2026-11-06;DI1F27;DI1;Taxa Média de Depósitos Interfinanceiros de Um Dia;FINANCIAL;FUTURE;;2027-01-04;F27;2015-12-28;2026-12-30;252;Exponential;100000;true;BRBMEFD1I4Z0;FFNCSX;;;;1;1;1;BRL;Financial;38;36;59;;;;;9800334;RTDI1;;;;Rate;;;;;;;;;;;;;;
```
2026-11-06 composition by `SgmtNm`: EQUITY CALL 36,162; EQUITY PUT 36,153; FINANCIAL 6,873; CASH 3,663; Equity Block Trading Lot 2,855; AGRIBUSINESS 1,917; EQUITY FORWARD 848; ODD LOT 519; FORWARD 77; ETF PRIMARY MARKET 77.

## 4. Quirks
- Latin-1; decimals in the CSV use `,` (`TradeInformationConsolidatedFile`: `13,662`; the Instruments file keeps `4,87` only inside text fields; numeric fields such as `CtrctMltplr` use `0,2`). Dates ISO `YYYY-MM-DD`; open-ended = `9999-12-31`.
- **Not a point-in-time universe by itself:** only 28 of 89,144 rows have `TradgEndDt` < `RptDt`, and 0 of 3,663 CASH rows. Delisted/expired instruments vanish from the file; the universe must be built by accumulating daily files (invariant 5, 13).
- Date-range requests: the file route is one date per call.

## 5. Identity fields
`TckrSymb` (TICKER), `ISIN`, `Asst` (root, e.g. PETR), `CFICd`, `CrpnNm` (issuer name only — no CNPJ), `UndrlygTckrSymb1/2`.

## 6. Ephemerality
Both files are **served for ~17 months (since 2025-06-10) and the start may roll**: archive daily from now, and **backfill 2025-06-10 → today immediately** (356 files × ~26 MB instruments + ~5 MB trades ≈ 11 GB uncompressed; CSV compresses well). Earlier history is not served by B3 on any route found; see "Recovery" below.
- Recovery before 2025-06-10: (1) **pesquisapregao `IN{YYMMDD}.zip` = BVBG.028.02 instrument registry, served from 2018-01-02** (see b3_settlement_prices.md; XML, content not parsed in this pass), plus `SecurityList` (from ≥ 2024), `II`; (2) the BDI PDF has no registry; (3) Internet Archive: `arquivos.b3.com.br/tabelas/*` has 0 captures (CDX prefix query returned empty; `/bdi/table/*` and `/api/download*` were not queried), host-wide the archive holds only the root page (2020-08) and `.well-known` 404s: **no tier-S copy exists** for this route.

## 7. BDI table catalog (`GET /bdi/table/classifications`, 75 tables; probed with POST `<d>/<d>/1/1` at 2026-11-06, 10-07, 10-06, 2026-04-01, 2025-12-15, 2025-12-10, 2025-06-10, 2025-01-02, 2023-01-02, 2020-01-02, 2015-01-02)
`config.js` of the BDI app says `minDate: 2022-01-01`. Oldest served = oldest probe date returning rows (so "≥ X" means a probe date, not the true limit).
| table | content | oldest served |
|---|---|---|
| ConsolidatedTradesEquities / ...RVAfter (671/677) | equity trades per instrument/day | 2026-10-07 (D-21) |
| ConsolidatedTradesDerivatives / ...After (672/676) | derivatives trades+settlement | 2026-10-07 |
| InstrumentsEquities (669) / InstrumentsDerivatives (668) | registry | 2026-10-07 |
| OpenPositionsEquities (670), AnalyticalFramework2 (692) | open interest / analytic frame (AnalyticalFramework2 empty 2026-11-06, so ≥ publication lag) | 2026-10-07 |
| BTBLendingOpenPosition (553), BTBLoanBalance (554), Renewals (667), BTBTrade (2000) | securities lending | 2026-10-07 |
| EconomicIndicators (565) | RT* indicator values (DOL, ZAR, …) | 2026-10-07 |
| TickByTick* (RV, Derivatives, BTBTrade) | tick data | request errors on every date probed (not usable here) |
| DerivativesMtM, DerivativesOperation2, DailyAverage*, StocksOperationSummary, ForwardMarket, IOPV, NegotiStrategi, MarginScenarios, Custody, ProventionCredit, FugibleCustody, DeadlineDeposit, SwapFlex, EletronicTerm, FlexibleOptions, OTCRegistration/Inventory(CCP/WCCP), COE*, SharesInvesVolum*, coffee tables, Ibovespa/Cash biggest highs/lows | misc. daily summaries | 2026-10-07 (or today only) |
| INDEXES (1034), PreviaQuadrimestral (1039), Previa (1040) | index evolution / theoretical-portfolio previews | empty at every probe date (not usable on the BDI; see b3_index_portfolio.md) |
| DebenturesBusiness (271), ConsolidatedRecords (529) | fixed-income trades on Puma | ≥ 2025-06-10, < 2025-01-02 (limitDate M-18) |
| Trade (528), SaleOff (531), Stock (532) | fixed-income trade-by-trade, settlement, stock | ≥ 2025-01-02, < 2023-01-02 |
| Register (673), RepurchaseDealings (674), Repodebenture (682), TDA (680) | fixed income | ≥ 2025-12-10, < 2025-06-10; B3 text: data before 2025-12-11 are on `https://drp.b3.com.br/Web/HistoricoRF` (SPA, **not explored**) |
| InstrumentRegistration (530) | OTC instrument list | today and D-21 only |
| **DIover (681)** | DI over (volume, average rate, daily factor, Selic) | **1986-03-06** (a single request `1980-01-01/2026-11-06/1/3` returns pageCount 3,388 rows from 1986-03-06): full history, range queries allowed |
| AverageChart (1031), HistoricalExchange (675, `PDC_ANO-5`) | annual-average volumes; BCB Res. 120 FX table | ≥ 2023-01-02, < 2020-01-02 |
Beyond these, the JSON `workdays` helper lists only 21 dates.

## 8. Open questions
- Is 2025-06-10 a fixed start? Re-probe next session.
- `drp.b3.com.br/Web/HistoricoRF` (renda fixa before 2025-12-11): not explored (SPA; its `config.js` points to `https://drp.b3.com.br/api/`).
- Terms of use of the arquivos.b3.com.br data (not checked); 11 GB backfill is large relative to "≤ 1 request/second" politeness (≈ 700 requests, fine).
