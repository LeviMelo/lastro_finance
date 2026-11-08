# context_global — global context series (US Treasury, NY Fed, ECB, BIS, Cboe, EIA, World Bank, IMF, OECD, CFTC, BLS, FRED)

**Tier:** P for each official publisher; U for Yahoo rows. **Recon date:** 2026-11-07 (all rows requested that day unless "not verified"). Wired: `src/fin/reference/context_series.toml` (ADR-0011). FRED and Tiingo need a free key (OQ-23): the owner's keys are in the git-ignored `secrets.toml` since 2026-11-08, and FRED is wired (`fred`, 28 series).
UA used: `lastro-fin/0.1.0 (personal research archiver; low request rate)`, <=1 req/s per host, curl. Date formats noted per source.
Verified column = Y + sample value from today's request.

## 1. US rates
| series | source | exact URL | first date | freq | lag | unit | keyless | verified |
|---|---|---|---|---|---|---|---|---|
| Par yield curve (1M..30Y; 1.5M/2M/4M added later; 1990 file has 3M..30Y) | US Treasury | `https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{YYYY}/all?type=daily_treasury_yield_curve&field_tdr_date_value={YYYY}&page&_format=csv` (one request per year; XML twin: `.../interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value={YYYY}`) | 1990-01-02 | daily (bus.) | same day evening (11/06/2026 present on 11/07) | % p.a. bond-equivalent, par | Y | Y: 2026-11-06 10Y 4.86, 2Y 4.51. `/all/all` bulk URL = HTTP 403 Access Denied (Akamai) -> loop years 1990..now (37 requests). Date format MM/DD/YYYY, newest first. |
| Real yield curve (TIPS par, 5/7/10/20/30Y; 2003 file only 5/10/20) | US Treasury | same pattern, `type=daily_treasury_real_yield_curve` | 2003-01-02 (2002 -> empty 0 bytes) | daily | same day | % p.a. real | Y | Y: 2026-11-06 10Y 2.63, 30Y 3.07 |
| LT real average (>10Y) | US Treasury | same pattern, `type=daily_treasury_real_long_term` | not verified (2026 only fetched) | daily | same day | % | Y | Y: 2026-11-06 3.05 |
| EFFR (+percentiles, volume, target range) | NY Fed Markets API | `https://markets.newyorkfed.org/api/rates/unsecured/effr/search.csv?startDate=1900-01-01&endDate={today}&type=rate` ; latest: `.../api/rates/unsecured/effr/last/N.json` | 2000-07-03 (7.03) | daily | T+1 (11-05 value on 11-07 morning; "all/latest" had 11-06 SOFRAI) | % | Y | Y: 2026-11-05 3.88, target 3.75-4.00; 380 KB / 6,622 rows full history |
| SOFR (+percentiles, volume) | NY Fed | `https://markets.newyorkfed.org/api/rates/secured/sofr/search.csv?startDate=2018-01-01&endDate={today}&type=rate` | 2018-04-02 (1.80) | daily | T+1 | % | Y | Y: 2026-11-05 3.92 |
| SOFR averages and index (30/90/180d, SOFRAI) | NY Fed | `https://markets.newyorkfed.org/api/rates/all/latest.json` (and `/secured/sofrai/...`) | not verified | daily | T+0/1 | % / index | Y | Y: 2026-11-06 30d avg 3.91294, index 1.26592422 |
| Other NY Fed rates (OBFR, TGCR, BGCR) | NY Fed | same API, `/rates/secured/tgcr`, `/bgcr`, `/unsecured/obfr` | not verified | daily | T+1 | % | Y | N (not requested separately; listed in `all/latest.json`, not parsed) |
Notes: NY Fed EFFR starts 2000 here; FRED `DFF`/`FEDFUNDS` goes back to 1954 (needs key; BIS WS_CBPOL US monthly goes to 1954-07 keyless, see section 2). Terms: not read for Treasury/NY Fed (US-government works, no key); not verified.
FRED codes worth having (keyed; not requested): DGS1MO..DGS30 (curve, also from Treasury), DFII5/DFII10 (TIPS), T10YIE/T5YIE/T5YIFR (breakevens, no Treasury original), DFF, SOFR, DTWEXBGS (broad dollar), DTWEXEMEGS, VIXCLS, BAMLH0A0HYM2 (HY OAS), BAMLEMCBPIEY, DCOILBRENTEU, DCOILWTICO, T10Y2Y, NFCI, WALCL, CPIAUCSL, UNRATE, PAYEMS, DEXBZUS, DEXCHUS.

## 2. Other central banks
| series | source | exact URL | first date | freq | lag | unit | keyless | verified |
|---|---|---|---|---|---|---|---|---|
| EUR short-term rate (EURSTR) | ECB Data Portal SDMX REST | `https://data-api.ecb.europa.eu/service/data/EST/B.EU000A2X2A25.WT?format=csvdata[&startPeriod=]` | 2019-10-01 (-0.549) | daily (TARGET) | T+1 (2026-11-05 on 11-07 morning) | % | Y | Y: 2026-11-05 2.442 |
| Euro AAA govt spot curve (Svensson), 10Y | ECB | `.../service/data/YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y?format=csvdata` (SR_1Y..SR_30Y, also `G_N_C` all-issuers) | 2004-09-06 (4.209) (2000-2004 query empty) | daily | T+1 | % | Y | Y: 2026-11-05 3.294 |
| EUR/USD reference rate (2.15pm CET) | ECB | `.../service/data/EXR/D.USD.EUR.SP00.A?startPeriod=1999-01-01&format=csvdata` (1.5 MB all-history; any ccy: D.BRL, D.CNY, D.JPY...) | 1999-01-04 (1.1789) | daily | same day (2026-11-06 on 11-07) | USD per EUR | Y | Y: 2026-11-06 1.1165 |
| EUR/BRL reference | ECB | `.../EXR/D.BRL.EUR.SP00.A` | not verified | daily | same day | BRL per EUR | Y | Y: 2026-11-06 6.1449 |
| ECB key rates (MRO fixed) | ECB | `.../service/data/FM/B.U2.EUR.4F.KR.MRR_FR.LEV` (also DFR, MLFR) | not verified | event (changes) | on change | % | Y | Y: 2026-09-16 2.65 (value as returned; interpret dated-change series) |
| Central bank policy rates, ~40 countries (BR, US, XM, GB, JP, CN, IN, MX, CL, ZA ...) | BIS SDMX v2 (flow WS_CBPOL) | `https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/{D|M}.{REF_AREA}[+..]?format=csv[&startPeriod=][&lastNObservations=]` | BR daily 1986-06-04 (17.8); US monthly 1954-07 | daily and monthly | daily to 2026-11-03 on 11-07 (T+2-4); monthly to 2026-10 | % | Y | Y: 2026-10 monthly US 3.875, XM 2.5, GB 3.75, JP 1.25, CN 3, MX 6.5, CL 4.5, ZA 7.25, BR 13.75, IN 5.25 (2026-09). WARNING: daily CSV repeats long COMPILATION text per row: BR daily all-history = 12.1 MB (breaks the 5 MB cap; I deleted it). Use monthly, or startPeriod windows. |
| Effective exchange rates (BIS EER, broad nominal BR) | BIS (WS_EER) | `.../data/dataflow/BIS/WS_EER/1.0/M.N.B.BR?format=csv` (R=real; N=nominal; B broad / N narrow) | not verified | monthly | ~1 month (2026-09 on 11-07) | index 2020=100 | Y | Y: BR nominal broad 2026-09 113.48 |
| BoE Bank Rate daily (IUDBEDR) | Bank of England IADB | `https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp?csv.x=yes&Datefrom=01/Jan/2026&Dateto=now&SeriesCodes=IUDBEDR&CSVF=TN&UsingCodes=Y&VPD=Y&VFD=N` | not verified (2026 window only) | daily | ~same day | % | Y | Y: 2026-01-02 3.75; 2026-11-05 4.00 |
Notes: BIS availability/dataflow listing with format=json -> 501/406; csv data endpoint works. ECB terms: re-use with attribution (not re-read today; not verified). BIS terms not read; not verified.

## 3. Equity and risk indicators
| series | source | exact URL | first date | freq | lag | unit | keyless? | verified |
|---|---|---|---|---|---|---|---|---|
| VIX (OHLC) | Cboe (official CDN, tier O) | `https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv` | 1990-01-02 (17.24) | daily | same day close (2026-11-06 on 11-07) | index pts | Y | Y: 2026-11-06 close 25.64 (11-05: 28.18); 475 KB, MM/DD/YYYY |
| VIX9D, VIX3M (OHLC) | Cboe | `.../daily_prices/VIX9D_History.csv`, `VIX3M_History.csv` | 2011-01-04 / 2009-09-18 | daily | same day | pts | Y | Y (headers and first rows) |
| SKEW | Cboe | `.../daily_prices/SKEW_History.csv` | 1990-01-02 (126.09) | daily | same day | index | Y | Y: 2026-11-06 153.55 |
| VVIX | Cboe | `.../daily_prices/VVIX_History.csv` | 2006-03-06 (71.73) | daily | same day | index | Y | Y (first rows; early gaps: 2006-03-06 then 03-15) |
| MOVE index | ICE BofA (paid; no official keyless) | Yahoo unofficial: `https://query1.finance.yahoo.com/v8/finance/chart/%5EMOVE?range=max&interval=1d` | 2002-11-12 (Yahoo firstTradeDate) | daily | same day | bp-vol index | Y but tier U | Y: ^MOVE 92.77 (latest) |
| S&P 500 index level | Yahoo chart API (tier U) | `https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?period1=-1325635200&period2={epoch}&interval=1d` | 1927-12-30 (17.66; price index) | daily | same day | pts, USD, price return only | Y but tier U; browser UA used (generic UA not tested) | Y: 24,831 rows, 2.6 MB, last 2026-11-06 7376.86 |
| S&P 500 (FRED copy) | FRED fredgraph.csv (see section 6 note) | `https://fred.stlouisfed.org/graph/fredgraph.csv?id=SP500` | 2016-11-07 (licence caps to 10 yrs) | daily | T+1 | pts | Y (undocumented UI endpoint) | Y: 2026-11-05 7353.73 |
| Ibovespa via Yahoo | Yahoo (U) | `.../chart/%5EBVSP` | 1993-04-27 (firstTradeDate) | daily | same day | BRL pts | tier U | Y: 168,498.45 (latest meta) |
| MSCI World (^990100-USD-STRD) | Yahoo (U); MSCI itself: not verified | `.../chart/%5E990100-USD-STRD` | 1972-01-03 (firstTradeDate) | daily | T+1 | index USD | tier U | Y: 4739.93 latest. MSCI EM symbol not requested (N). EEM ETF as proxy: Y: 59.33, from 2003-04-14 |
| Nasdaq Composite | FRED csv | `fredgraph.csv?id=NASDAQCOM` | 1971-02-05 (100) | daily | T+1 | pts | Y | Y |
| Cboe delayed-quotes historical `_SPX.json` | Cboe | `https://cdn.cboe.com/api/global/delayed_quotes/charts/historical/_SPX.json` | | | | | | N: HTTP 200, 0 bytes (unusable) |
Notes: Yahoo is tier U (no redistribution licence; ToS not read today). No official keyless S&P/MSCI level history found; FRED carries only trailing windows (SP500 10y, ICE BofA 3y).

## 4. FX
| series | source | exact URL | first date | freq | lag | unit | keyless? | verified |
|---|---|---|---|---|---|---|---|---|
| EUR vs USD, BRL, CNY, JPY ... ECB reference | ECB | section 2 (`EXR/D.{CCY}.EUR.SP00.A`) | 1999-01-04 (USD) | daily | same day | ccy per EUR | Y | Y (USD, BRL) |
| Broad dollar index (Fed, goods+services) | FRED `DTWEXBGS` (Fed H.10 original not located) | `https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTWEXBGS` | 2006-01-02 (101.4155) | daily | ~1 week (last obs 2026-10-30 on 11-07) | index Jan 2006=100 | Y (undocumented UI endpoint) | Y: 2026-10-30 121.6656 |
| USD/BRL (H.10) | FRED `DEXBZUS` | `fredgraph.csv?id=DEXBZUS` | 1995-01-02 (0.8440) | daily | ~1 week | BRL per USD | Y | Y: 2026-10-30 5.4252 |
| DXY (ICE) | ICE: paid; Yahoo `DX-Y.NYB` (U) | `.../chart/DX-Y.NYB?range=max` | 1971-01-04 (firstTradeDate) | daily | same day | index | tier U | Y: 102.279 latest |
| USD/CNY | Yahoo `CNY=X` (U); ECB `D.CNY.EUR` as official cross (not requested) | `.../chart/CNY%3DX` | 2001-06-24 (firstTradeDate) | daily | same day | CNY per USD | tier U | Y: 6.6648 |
| BIS effective exchange rates | BIS | section 2 | not verified | monthly | ~5 weeks | index | Y | Y |
Fed H.10 direct feed (federalreserve.gov/releases/h10): not requested today (N).

## 5. Commodities and positioning
| series | source | exact URL | first date | freq | lag | unit | keyless? | verified |
|---|---|---|---|---|---|---|---|---|
| Pink Sheet monthly (Brent, WTI, Dubai, coal, gas, iron ore cfr, copper, aluminium, gold, silver, soy, maize, sugar, coffee, urea, ~70 cols + indices) | World Bank | `https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/CMO-Historical-Data-Monthly.xlsx` (hash changes each release: scrape the link from `https://www.worldbank.org/en/research/commodity-markets`); annual: `...-Annual.xlsx` | 1960M01 | monthly | ~3 days after month end (file "Updated on November 03, 2026", last col 2026M10) | nominal USD (units per column; indices 2010=100) | Y | Y: 588 KB. 2026M10: Brent 125 $/bbl, iron ore cfr 90.8 $/dmtu, copper 14,508 $/mt, gold 4,105 $/toz, soy 515 $/mt. Some early cells are non-numeric placeholders. Licence not read: not verified. |
| Brent spot FOB | EIA | `https://www.eia.gov/dnav/pet/hist_xls/RBRTEd.xls` (sheet "Data 1", Excel serial dates) | 1987-05-20 (18.63) | daily | ~3 days (last 2026-11-03 on 11-07) | USD/bbl | Y | Y: 2026-11-03 107.03; 453 KB, xlrd reads it |
| WTI Cushing spot | EIA | `https://www.eia.gov/dnav/pet/hist_xls/RWTCd.xls` | 1986-01-02 (25.56) | daily | ~3 days | USD/bbl | Y | Y: 2026-11-03 99.64 |
| Brent/WTI FRED copies | FRED csv | `fredgraph.csv?id=DCOILBRENTEU` / `DCOILWTICO` | 1987-05-20 / 1986-01-02 | daily | ~3-4 days | USD/bbl | Y | Y: WTI 2026-11-03 99.64 (= EIA) |
| Futures: copper HG, gold GC, Brent BZ, iron ore TIO (SGX 62% Fe) | Yahoo (U) | `.../chart/{HG%3DF,GC%3DF,BZ%3DF,TIO%3DF}` | HG/GC 2000-08-30; BZ 2007-07-30; TIO 2010-10-14 (firstTradeDate) | daily | same day | USD | tier U | Y: HG 6.238 $/lb, GC 4074.9, BZ 98.32, TIO 161.91 (continuous front month; roll gaps, unadjusted) |
| LBMA gold fix | LBMA/ICE licensed | n/a | | | | | N | N (not requested; paid/licensed). Alternatives: WB monthly gold; Yahoo GC=F |
| Dalian/SGX iron ore daily (official) | DCE/SGX | n/a | | | | | | N (not requested; assumed paid). WB monthly + Yahoo TIO=F as proxies |
| CFTC COT legacy, futures only, 1986 -> | CFTC | per-year `https://www.cftc.gov/files/dea/history/deacot{YYYY}.zip` (listed 1986..2026; the combined `deacot1986_2016.zip` is 22.9 MB: over our cap); index `https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalCompressed/index.htm` | 1986 (per index page; per-year 1986 file not fetched) | weekly (Tuesday as-of) | published Friday (3 days) | contracts | Y | Y: deacot2026.zip 2.2 MB, member `annual.txt` |
| COT Disaggregated (commodities) | CFTC | `https://www.cftc.gov/files/dea/history/fut_disagg_txt_{YYYY}.zip` (2010-2026), `fut_disagg_txt_hist_2006_2016.zip`; futures+options `com_disagg_txt_{YYYY}.zip` | 2006 (index page) | weekly | 3 days | contracts | Y | Y: com_disagg_txt_2026.zip 2.2 MB, `c_year.txt`, 12,326 rows, latest Report_Date 2026-11-03 |
| COT TFF (UST, S&P, FX, VIX futures) | CFTC | `https://www.cftc.gov/files/dea/history/fut_fin_xls_{YYYY}.zip` / `fut_fin_txt_{YYYY}.zip`, `fin_fut_txt_2006_2016.zip` | 2006 | weekly | 3 days | contracts | Y | Y: fut_fin_xls_2026.zip 1.4 MB fetched (not parsed) |

## 6. Global macro
| series | source | exact URL | first date | freq | lag | unit | keyless? | verified |
|---|---|---|---|---|---|---|---|---|
| IMF Primary Commodity Prices (PCPS): Brent, WTI, Dubai, iron ore, copper, gold, soybeans, ... + indices | IMF SDMX 2.1 (new API) | `https://api.imf.org/external/sdmx/2.1/data/PCPS/G001.{INDICATOR}.USD.M` (dims COUNTRY.INDICATOR.DATA_TRANSFORMATION.FREQUENCY; indicators POILBRE, POILWTI, POILDUB, PIORECR, PCOPP, PGOLD, PSOYB ...; transforms USD, INDEX, INDEX_PCH, INDEX_PCHY; wildcard dump `data/PCPS/...M?lastNObservations=1` = 404 series, 106 KB) | 1992-M01 (Brent 18.157, iron ore 14.31) | monthly (also A, Q) | ~5 weeks (2026-M09 on 11-07; WB Pink Sheet is faster) | USD (monthly avg) / index 2016=100 | Y (generic UA works) | Y: 2026-M09 Brent 102.018, iron ore 100.441, copper 14,473.06, gold 4,334.75. Licence field in each message: "(c) IMF, All Rights Reserved, https://www.imf.org/external/terms.htm" (terms not read: redistribution restricted; treat as personal-use). |
| IMF CPI (national, all items, index) | IMF SDMX 2.1 | `https://api.imf.org/external/sdmx/2.1/data/CPI/BRA.CPI._T.IX.M` (dims COUNTRY.INDEX_TYPE.COICOP_1999.TYPE_OF_TRANSFORMATION.FREQUENCY) | not verified | monthly | ~5-6 weeks (2026-M09) | index, ref 1993M12 for BRA | Y | Y: BRA 2026-M09 7695.82 |
| IMF WEO (GDP growth etc.) | IMF SDMX 2.1 | `https://api.imf.org/external/sdmx/2.1/data/WEO/BRA.NGDP_RPCH.A` (dims COUNTRY.INDICATOR.FREQUENCY; vintages `WEO_2026_APR_VINTAGE`, `WEO_2025_OCT_VINTAGE` also exist as flows) | 1980 (9.19) | annual, 2 releases/yr | vintage dates | % | Y | Y: BRA 2026 forecast 2.182 (country update 9/24/2026), 2027 1.863. WEO flow lists current only; discover flows at `https://api.imf.org/external/sdmx/3.0/structure/dataflow` (231 flows, 396 KB). |
| IMF IFS | n/a | old `dataservices.imf.org/REST/SDMX_JSON.svc/...` | | | | | | N: host NXDOMAIN (nslookup: non-existent domain) = retired. No IFS flow found in the new dataflow list (CPI, BOP, PCPS, CTOT... present); not verified further. |
| IMF DataMapper API | IMF | `https://www.imf.org/external/datamapper/api/v1/NGDP_RPCH/BRA` | | | | | | N: HTTP 403 Akamai "Access Denied" with generic AND browser UA; `https://www.imf.org/en/Research/commodity-prices` also 403. api.imf.org is the working route. In-app browser not tried. |
| OECD CLI (Brazil, amplitude adjusted `LI`, others LOCOBP/LOCOSP...) | OECD SDMX REST | `https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI,4.1/BRA.M.LI...AA...H?format=csv` (all-history 39 KB) | 1993-01 (99.57) | monthly | ~5-6 weeks (2026-09) | index, long-term avg=100 | Y | Y: BRA LI 2026-09 101.7754 (AA series 102.3614 / 101.7754 variants as listed). Terms not read. |
| OECD CPI (all items, index/yoy) | OECD SDMX REST | `https://sdmx.oecd.org/public/rest/data/OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0/{AREA}.M.N.CPI.{IX|PA}._T.N.{_Z|GY}?format=csv` | USA GY series from at least 2023 (earliest row not checked): N | monthly | ~5 weeks | index / % yoy | Y | Y: BRA CPI IX 2026-09 178.5524; USA yoy 2023-11 3.137 (first rows). Do NOT call `/dataflow/all` (8.9 MB). |
| World Bank WDI indicators | World Bank API v2 | `https://api.worldbank.org/v2/country/{ISO3|all}/indicator/{CODE}?format=json&per_page=N&date=YYYY[:YYYY]` | per indicator (not checked) | annual (some monthly in other sources) | WDI updated 2026-10-08 (field `lastupdated`) | per indicator | Y | Y: BRA NY.GDP.MKTP.CD 2025 = 2,279,920,092,492 USD; 66 obs; FP.CPI.TOTL.ZG all-countries 2024 returns. Licence CC BY 4.0 per WB data policy (not re-read today: not verified) |
| BLS CPI-U NSA (CUUR0000SA0), payrolls (CES0000000001), unemployment (LNS14000000) | BLS Public Data API v1 | GET `https://api.bls.gov/publicAPI/v1/timeseries/data/{SERIES}` (latest ~3 yrs, ignores startyear on GET) ; POST JSON `{"seriesid":[..],"startyear":"2025","endyear":"2026"}` to `https://api.bls.gov/publicAPI/v1/timeseries/data/` | per series (CPI-U from 1913 in principle: not verified) | monthly | CPI Sep 2026 published; payrolls/unemp for Oct 2026 already out | index / thousands / % | Y (v1, no key; no email demanded in UA; generic UA accepted) | Y: CPI-U Sep 2026 336.940; CES0000000001 Oct 2026 159,293 (k); LNS14000000 Oct 2026 4.1. v1 limits (BLS docs, not re-verified): 25 queries/day, 10 years/query, 25 series/query. Flat files `https://download.bls.gov/pub/time.series/cu/cu.data.0.Current`: HTTP 403 (AkamaiGHost) with generic and browser UA -> N (BLS asks for contact in UA there; not provided). |
| FRED keyless graph CSV (undocumented UI endpoint) | St. Louis Fed | `https://fred.stlouisfed.org/graph/fredgraph.csv?id={SERIES}` (one id per request; comma-list returned a zip with README + daily.csv) | per series | per series | per series | per series | Y (no key, generic UA; browser UA once got connection reset; `robots.txt` also reset) | Y: DGS10 from 1962-01-02 (4.06), last 2026-11-05 4.84; DTWEXBGS, DEXBZUS, DCOILWTICO, CPIAUCSL (1947-01-01, 2026-09 336.298), SP500, NASDAQCOM, BAMLH0A0HYM2 (only 2023-11-07 -> : 3y licence window, 2026-11-05 3.48), T10YIE 2003-01-02 (1.64) to 2026-11-06 2.23. README: "This data may be copyrighted. Refer to Terms of Use https://fred.stlouisfed.org/legal#fred-terms-faq" (terms page not read). Not an official API: fragile, tier O-undocumented; the official keyed API stays the supported route. |
| China NBS | National Bureau of Statistics | `https://data.stats.gov.cn/easyquery.htm?cn=A01` and `/english/easyquery.htm?cn=A01` | | | | | | N: HTTP 403 (nginx "Client IP ...") with generic and browser UA from a Brazilian IP, i.e. a firewall/geo block rather than DNS/TLS failure; `https://www.stats.gov.cn/english/` = 200 (25 KB landing page). In-app browser not tried; terms not read. Alternatives: IMF/OECD/World Bank China series, FRED copies, and BIS CN policy rate (verified above). |

FRED series list worth having (keyed API or keyless graph CSV above): DGS2/5/10/30, DFII10, T10YIE, T5YIFR, DFF, SOFR, DTWEXBGS, DEXBZUS, DEXCHUS, VIXCLS, DCOILBRENTEU, DCOILWTICO, GOLDAMGBD228NLBM (LBMA gold on FRED; licence may have been removed: not verified), PCOPPUSDM (IMF copper), PIORECRUSDM (IMF iron ore), CPIAUCSL, UNRATE, PAYEMS, NFCI, STLFSI4, WALCL, BAMLEMHBHYCRPIOAS (3y window), T10Y2Y, USREC.

## 7. Python libraries (PyPI JSON, requested today)
| package | latest | released | licence | note |
|---|---|---|---|---|
| sdmx1 | 2.28.0 | 2026-10-18 | Apache-2.0 (classifier) | py>=3.11; successor to pandasdmx; sources include ECB, BIS, IMF, OECD, ESTAT, WB. Not tested against api.imf.org today. |
| pandasdmx | 1.10.0 | 2023-02-25 | Apache-2.0 | superseded; py<3.12: do not use |
| wbgapi | 1.0.14 | 2026-02-27 | MIT | World Bank API |
| fredapi | 0.5.2 | 2024-05-05 | no licence metadata on PyPI (repo: MIT, not checked) | needs key; stale 2.5 yrs |
| pandas-datareader | 0.11.1 | 2026-06-24 | BSD-3-Clause | FRED/WB/Stooq etc. wrappers |
| python-bcb | 0.4.1 | 2026-10-23 | no metadata on PyPI | BCB SGS/PTAX/Focus (the Brazilian side; not tested) |
| yfinance | 1.8.0 | 2026-11-03 | Apache-2.0 | Yahoo scraper, tier U |
| tiingo | 0.16.1 | 2025-04-05 | MIT | key needed |
| cot-reports | 0.1.3 | 2023-12-29 | MIT | stale; CFTC zips are simple enough to parse directly |
| eurostat | 1.1.1 | 2024-06-13 | MIT | Eurostat (not needed so far) |
| xlrd 2.0.2 (already in repo, read EIA .xls fine) / openpyxl 3.1.5 (MIT; needed for the WB Pink Sheet .xlsx, NOT in repo env: I used `uv run --no-project --with openpyxl`) / python-calamine 0.9.1 (MIT, 2026-11-03) / fastexcel 0.21.0 (MIT, polars-native xlsx) | | | | polars is in the repo env; fastexcel is the lightest fit for Pink Sheet |
Recommendation: `httpx` + `polars` for the CSV/SDMX-CSV routes (all verified above are plain HTTP CSV/XML/JSON); add `fastexcel` or `openpyxl` for Pink Sheet; `sdmx1` optional (BIS/ECB/IMF/OECD all answer SDMX-CSV directly via URL).

## 8. Compliance and caveats of this recon
- Per-file 5 MB cap exceeded three times by mistake (guessed/unfiltered requests): BIS WS_CBPOL daily BR all-history 12.1 MB (deleted), CFTC `deacot1986_2016.zip` 22.9 MB (deleted), OECD `dataflow/all` 8.9 MB (deleted); total on disk at end ~16 MB, total transferred <60 MB (<150 MB cap).
- <=1 request/s per host held (1.2-1.5 s sleeps). No logins, no keys, no CAPTCHA/JS challenge met. HTTP 403 Akamai on: Treasury `/all/all` bulk, IMF www.imf.org (datamapper, commodity-prices), BLS download.bls.gov, NBS data.stats.gov.cn. Connection reset (not 403) on fred.stlouisfed.org robots.txt and once on browser UA: not diagnosed with curl -v.
- Yahoo requests used a plain browser UA; BLS/SEC contact-info expectation not met (no email added).
- Not requested at all: Fed H.10 feed, Eurostat, BoE beyond Bank Rate, ICE/MSCI/LBMA/DCE official pages, terms of use for any source (licences above are labels read from payloads or "not verified").

## Parsed into `series_observation` (2026-11-07, ADR-0013)
- **us_treasury:** `us_treasury:{par,real}/<tenor>` (1M…30Y; headers `1 Mo`, `1.5 Month`, `10 Yr`, real `10 YR`). Tenors
  appear as columns are added (1M 2001-07-31, 2M 2018-10-16, 4M 2022-10-19, 1.5M 2025-02-18); an empty cell yields no
  row. 2026-11-06: par 10Y 4.86, real 10Y 2.63.
- **nyfed:** `nyfed:{EFFR,SOFR}/<field>` from the headers' units (`(%)`, `($Billions)`). EFFR intraday low/high and
  standard deviation run 2000-07-03 → 2016-02-29; percentiles and volume from 2016-03-01. SOFR percentiles read `NA`
  on 2019-05-31 and 2021-08-05 (kept as missing). `Revision Indicator` ('r') and `Footnote ID` stay in raw.
- **cboe:** `cboe:<INDEX>/{OPEN,HIGH,LOW,CLOSE}`; VVIX and SKEW files carry only the close. VIX 1990-01-02 → 2026-11-06.
- **ecb, bis, oecd (SDMX-CSV):** ids `<source>:<series key>` (ECB's `KEY` column; BIS and OECD from the flow's
  dimensions). Units are codes: ECB `UNIT` (PCPA, PC, BRL…), BIS/OECD `UNIT_MEASURE` (368, 882, IX). They are labelled
  from the sources' codelists, archived monthly:
  - ECB `service/codelist/ECB/CL_UNIT` (XML);
  - BIS `api/v2/structure/codelist/BIS/CL_BIS_UNIT/1.0` (JSON; the `latest` alias also works);
  - OECD `rest/datastructure/OECD.SDD.STES/DSD_STES/4.1?references=codelist` (1.6 MB;
    `rest/codelist/OECD.SDD.STES/CL_UNIT_MEASURE` answers 404).
  ECB frequency `B` (business days) is read as daily.
- **worldbank_cmo:** sheet "Monthly Prices" only: 71 commodities 1960-01→, units from the units row (`$/bbl`, `$/mt`);
  `…`/`...` = not available; 4 `#VALUE!` cells (Rice, Thai 25%) quarantined. The index sheet is not parsed yet.
- **eia:** `eia:RBRTE`, `eia:RWTC`, unit from the name's parenthesis (Dollars per Barrel); Excel date serials.
- **imf:** `imf:PCPS.G001.<indicator>.USD.M`; units from IMF's `CL_PCPS_INDICATOR` (archived monthly).
- **Cross-check 1992-01→ (417 months):** IMF vs World Bank gold and copper agree (median 0.05 %, max 1.2 %); Brent
  does not (median 0.64 %, max 15 %): IMF "Dated Brent" and the World Bank's "UK Brent 38 API" are different series.
- **cftc_cot:** staged long (`ingest/cftc.py`): one row per (report, market, Tuesday, trader group, side) for the
  "All" positions and open interest. Legacy 771 markets, disaggregated 630, financial 141 (from 2010-07-20); 5.17 M
  rows, 20 MB. Older files put a space after a closing quote, which a strict CSV reader refuses; Python's csv reads it.
  The disaggregated and financial reports of 2010-2012 name their date column `Report_Date_as_MM_DD_YYYY` but hold
  ISO dates. Changes, percentages and trader counts stay in raw.

## FRED API (measured 2026-11-08 with the owner's key)
- `https://api.stlouisfed.org/fred/series/observations?series_id=DGS10&api_key=…&file_type=json`: 200 JSON, header fields (realtime_start/end, count, limit 100000) and `observations[{realtime_start, realtime_end, date, value}]`; a missing value is `.`. `fred/series?series_id=…` gives title, frequency_short, units, seasonal_adjustment_short, observation_start (DGS10: 1962-01-02).
- Tier S: FRED redistributes other publishers' series (ICE BofA spreads under licence windows; S&P 500 10 years). The rows are the current vintage; ALFRED (`realtime_start`/`realtime_end` parameters) keeps earlier vintages and is not requested yet.

## Tiingo API (measured 2026-11-08 with the owner's token)
- `https://api.tiingo.com/tiingo/daily/spy/prices?startDate=…&endDate=…` with header `Authorization: Token …`: 200 JSON list of `{date, open, high, low, close, volume, adjOpen…adjVolume, divCash, splitFactor}`; `…/tiingo/daily/spy` gives name, description, exchangeCode, startDate, endDate. Wired as `tiingo` (`ingest/tiingo.py`), 17 tickers.
