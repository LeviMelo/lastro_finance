# b3_index_portfolio — B3: carteiras teóricas de índices (Ibovespa, IBrX, SMLL, IFIX, ...)

**Tier:** P (for current composition); history tier S (Internet Archive). **Recon date:** 2026-11-07. **Fixture:** `tests/fixtures/b3_index_portfolio/` (README has requests and sha256).

## 1. Access
- The B3 page `…/indices-amplos/indice-ibovespa-ibovespa-composicao-da-carteira.htm` iframes the SPA `https://sistemaswebb3-listados.b3.com.br/indexPage/day/<INDEX>?language=pt-br`, which calls (JS read from `main-es2015.*.js`) `GET https://sistemaswebb3-listados.b3.com.br/indexProxy/indexCall/<Endpoint>/<base64(json)>` with browser UA, no auth. Endpoints in the JS: `GetPortfolioDay`, `GetTheoricalPortfolio`, `GetStockIndex`, `GetDownloadPortfolioDay`, `GetDownloadPortfolioSegment`, `GetDownloadPortfolioTheorical`, `GetDownloadPreview`, `GetListDownloadStocks`.
- Request json for lists: `{"language":"pt-br","pageNumber":1,"pageSize":120,"index":"IBOV","segment":"1"}`; for downloads `{"index":"IBOV","language":"pt-br"}` (response = base64 of a `;` CSV, Latin-1).
- **No date/year/period parameter exists** in any call in the JS; extra keys (`date`, `year`, `quadrimester`) sent to `GetTheoricalPortfolio` were ignored (identical response) on 2026-11-07.
- Index codes accepted (measured, `GetPortfolioDay`, rows): IBOV 76, IBXX (IBrX 100) 100, IBXL (IBrX 50) 50, SMLL 103, IFIX 94, IDIV 51, MLCX 44, IFNC 17, ICON 58, IEEX 12, IMOB 15, ISEE 68, ICO2 61, UTIL 16. `IBRX100` returns null. BDI tables `INDEXES`, `Previa`, `PreviaQuadrimestral` returned nothing at any date probed (see b3_instruments.md).

## 2. Datasets
| dataset_id | granularity | history depth | cadence | URL pattern |
|---|---|---|---|---|
| GetPortfolioDay | "carteira do dia": theoretical quantity and weight per asset (header.date `09/11/26` on a Saturday 2026-11-07: it is the portfolio **valid for the next session**) | **current only** | daily | indexProxy/GetPortfolioDay/… |
| GetTheoricalPortfolio / GetDownloadPortfolioTheorical | quadrimestral theoretical portfolio (file title `IBOV - Carteira Set. a Dez. 2026`) | **current only** | 3 per year (Jan–Apr, May–Aug, Sep–Dec) | … |
| GetDownloadPreview | next-quadrimester preview (`Prévia Set. a Dez. 2026`) | current only (while a preview exists) | — | … |
| IndexStatistics `GetPortfolioDay` | **index level** (daily close), not composition | **IBOVESPA from 1968** (measured: 1968 and 1990 return data; the 1968 monthly minimum for January is 97,20) | daily | `https://sistemaswebb3-listados.b3.com.br/indexStatisticsProxy/IndexCall/GetPortfolioDay/<b64 {"index":"IBOVESPA","language":"pt-br","year":"1968"}>` |
| pesquisapregao `IR{YYMMDD}.zip` (BVBG.087 index report) | index levels, IOPV | 2016-11-07 present, 2015-11-06 absent | daily | see b3_settlement_prices.md |
So the composition history is **not on any B3 endpoint found**; only index levels have deep history.

## 3. Layout (GetPortfolioDay / GetTheoricalPortfolio)
`{"page":{pageNumber,pageSize,totalRecords,totalPages},"header":{"date":"09/11/26","part":"100,000","theoricalQty":"93.803.750.400","reductor":"13.997.077,41817488"},"results":[{"cod":"ABEV3","asset":"AMBEV S/A","type":"ON","part":"2,654","theoricalQty":"4.043.349.180"},…]}`
Strings use pt-BR formats (`.` thousands, `,` decimal). Sum of `part` = 100,000 (day) and 99,996 (quadrimester, rounding) on the 76 IBOV rows; `reductor` = divisor (redutor). `type` carries the class and listing segment (`ON      NM`).
```
{"segment":null,"cod":"ABEV3","asset":"AMBEV S/A","type":"ON","part":"2,654","partAcum":null,"theoricalQty":"4.043.349.180"}
```

## 4. Quirks
- `part` differs between GetPortfolioDay (opening-day weights, ABEV3 2,654) and GetTheoricalPortfolio (quadrimester weights, ABEV3 2,450): two different bases; both must be stored with their date.
- The date in `header.date` has 2-digit year (`dd/MM/yy`).

## 5. Identity fields
`cod` (TICKER), `asset` (short name only; no ISIN/CNPJ).

## 6. Ephemerality and history routes (all tried)
1. B3 JSON/CSV: current portfolio only → **archive daily** (`GetPortfolioDay` for each index, plus the theoretical portfolio and preview downloads whenever they change).
2. BDI JSON tables: empty (above). **BDI daily PDF (`https://arquivos.b3.com.br/bdi/download/bdi/<date>/BDI_00_<YYYYMMDD>.pdf`, served 2022-03-01 → yesterday, see b3_instruments.md)** contains the section "Composição das carteiras de índices" (2026-11-05: p.1036-1064): 31 index portfolios with theoretical quantity and weight (IBOVESPA, IGCX, IBRX50, IBXX, SMLL, MLCX, ICON, IMOB, IFNC, IDIV, IFIX, BDRX, IGNM, IBLV, …). Row format after text extraction: `ABCB4|ABC BRASIL|PN      N2|125.516.511|0,0642` (ticker, name, type, theoretical quantity, weight %). This is the only B3-official route to composition history found (≈ 4.7 years, daily, 32 MB per day); extraction is fragile, and I did not check whether the weights equal GetPortfolioDay's (not verified).
3. **Internet Archive (tier S).** CDX `https://web.archive.org/cdx/search/cdx?url=bvmf.bmfbovespa.com.br/indices/ResumoCarteiraTeorica.aspx&matchType=prefix&filter=statuscode:200&output=json` → **103 captures, 2016-05-05 → 2026-05-12** (per year: 2016 1, 2017 5, 2018 8, 2019 11, 2020 22, 2021 21, 2022 11, 2023 2, 2024 12, 2025 6, 2026 4; 103 distinct digests) over indices IBOV (~45 incl. spelling variants), IFIX, IDIV, IBXL, SMLL, ICON, BDRX, Ibrx… Capture bodies are 16–20 KB HTML tables with the full portfolio. One capture fetched (`web/<ts>id_/<url>`): a 2025-02-19 capture of the legacy page still showed "Carteira do Dia - 02/03/21", i.e. the legacy page was stale/frozen, so **the content date must be read from the page, not the capture timestamp**, and many captures after 2021 may be stale. The first body fetch after a burst of CDX calls returned HTTP 429 ("suspected abusive bot traffic"), a retry after ~10 minutes worked: space requests ≥ 2 s.
   `sistemaswebb3-listados.b3.com.br/indexProxy/*` has **0 captures**; `www.b3.com.br/pt_br/.../indice-ibovespa-ibovespa-composicao-da-carteira.htm` has captures from 2018-10 (shell page, 7 KB; not the data).
4. Not tried: B3 historical "carteiras" spreadsheets referenced by older pages (not found linked on the pages fetched), index methodology PDFs, third-party vendors.

## 7. Open questions
- Coverage of Internet Archive quadrimester portfolios per index (how many distinct real composition dates) needs a fetch of all 103 captures (not done).
- Whether `segment` values other than `"1"` (sectoral view) change the output *(not verified)*.
