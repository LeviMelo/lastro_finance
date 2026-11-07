# context_br — Brazilian economic and market context series (BCB, IBGE, Ipeadata, Focus, B3 indices, ANBIMA IMA, CEPEA, ANP)

**Tier:** P (BCB, IBGE, B3, ANBIMA, ANP), S (Ipeadata, CEPEA). **Recon date:** 2026-11-07. Wired: `src/fin/reference/context_series.toml` (ADR-0011). Terms: ADR-0012.

Every row: a request made on 2026-11-07 (Y + sample) or "N (not verified)". 
Conventions: SGS = `https://api.bcb.gov.br/dados/serie/bcdata.sgs.<code>/dados?formato=json` (daily series: 10-year window cap -> HTTP 406; monthly: whole history, no dates). `ultimos/N` works for all. Names/units/start from BCB CKAN (`dadosabertos.bcb.gov.br`, licence ODbL) unless marked "name n/v" (name not verified: CKAN has no record and the SGS metadata page www3.bcb.gov.br/sgspub/... answers 502 "Requisição inválida" to curl and a browser UA).
SIDRA = `https://apisidra.ibge.gov.br/values/t/<table>/n1/all/v/<var>/p/<period>` ; metadata `https://servicodados.ibge.gov.br/api/v3/agregados/<t>/metadados`.
IPEADATA = `https://www.ipeadata.gov.br/api/odata4/ValoresSerie(SERCODIGO='<code>')`.
"Lag" = observed vs 2026-11-07 (latest observation date in the answer) unless "docs". Sign conventions are marked.
SGS caveat seen today: `433 ultimos` and a dated full fetch intermittently answered HTTP 304 with empty body from the BCB proxy; `ultimos/N` retried OK.

## 1. Monetary / rates
| series | source | code / URL | first | freq | lag | unit | verified |
|---|---|---|---|---|---|---|---|
| Selic target (Copom meta) | SGS | 432 (daily, dated rows are filled forward INCLUDING FUTURE DATES: last row 09/12/2026 = 13.75, i.e. next Copom day; do not treat future rows as observed) | 1999-03-05 | daily | same day; future-filled | % a.a. | Y 13.75 |
| Copom meetings table (no.1 1996-06-26 .. no.282 2026-11-04): meeting date, extraordinary flag, bias (alta/baixa/sem viés/n/a), meta, vigência start/end, Selic efetiva in vigência (% period and annualised) | bcb.gov.br site JSON (no auth, browser UA) | `https://www.bcb.gov.br/api/servico/sitebcb/historicotaxasjuros` (found via in-app browser on /controleinflacao/historicotaxasjuros) | 1996-06-26 | per meeting (8/yr) | same day | meta % a.a.; efetiva % | Y 290 rows, 102 KB; #282 2026-11-04 meta 13.75 (#280 2026-08-05 14.00 -> #281 09-16 13.75) |
| Copom calendar (future meetings), atas | bcb.gov.br | `/api/servico/sitebcb/copomtaxaselic/...`, `/copom/atas_detalhes`, `/copomcalendario` (guessed paths) -> 400/500 | - | - | - | - | N: guessed URLs failed; real calendar/ata route not found. Past meeting dates come from the table above; the Dec-2026 date is inferable only from SGS 432's last row. |
| Selic effective daily | SGS | 11 (% a.d.) / 1178 (annualised b252, ultimos/1 answered 304 empty today) | 1986-06-04 | daily | D-1 | % a.d. / % a.a. | Y(11 via note), 1178 N today (304) |
| Selic accumulated month | SGS | 4390 (% a.m.), 4189 (annualised b252) | 1986-07/08 | monthly | month-end | % a.m./a.a. | Y 4390 first 01/08/1986=2.57 last 01/11/2026=0.20; 4189 last 13.65 |
| CDI daily / annualised | SGS | 12 / 4389 | 1986-03-06 | daily | D-1 | % a.d./% a.a. | (already in repo, bcb_sgs note) |
| TR | SGS | 226 (daily-start dates, row has `dataFim` = +1 month) | n/v | daily start, monthly rate | forward-dated to 05/12/2026 | % per period | Y last `05/11/2026->05/12/2026 = 0.1695`; name n/v |
| Poupança | SGS | 195 (from 04.05.2012), 25 (until 03.05.2012) | 2012-05-04 / 1991-02-01 | daily start, monthly rate | forward-dated | % a.m. | Y 195 last 05/11/2026=0.6703 |
| Real interest ex-ante | derived | Focus IPCA 12m-ahead (Section 7: `ExpectativasMercadoInflacao12Meses`, 2001-11-07) vs DI1/TS curve (B3) or Selic meta | 2001-11 | daily | ~1 week (Focus) | % a.a. | N (derivation, no series exists; inputs verified in S7) |
| Reserve requirements | SGS | CKAN has 1847/1848 (recolhimentos obrigatórios, R$ thousand, monthly from 1980) | 1980-01 | monthly | n/v | R$ thousand | N (listed in CKAN only; optional) |

## 2. Inflation
| series | source | code / URL | first | freq | lag | unit | verified |
|---|---|---|---|---|---|---|---|
| IPCA headline % m/m | SGS 433 ; SIDRA 1737 v63 (also index v2266, 3m v2263, 6m v2264, YTD v69, 12m v2265) | SGS 433 ; SIDRA t1737 | SIDRA 1979-12 | monthly | ~10th of next month (Sep-2026 out; Oct not yet) | % ; index Dec-1993=100 | Y 433 ultimos: 01/08/2026=-0.32, 01/09/2026=0.82; SIDRA 1737 meta 197912-202609 |
| IPCA by group/subgroup/item, weights, N6/N7 | SIDRA t7060 (2020-01 ->; vars 63, 69, 2265, 66 peso) ; t2938 (2006-07..2011-12, old) | `/t/7060/n1/all/v/63/p/last/c315/7169` (c315 7169 = índice geral) | 2020-01 (t7060) | monthly | same as IPCA | % | Y t7060 Sep-2026 = 0.82; t2938 range from metadata only |
| IPCA-15 | SIDRA t3065 (index v1117, m/m v355, 3m 1118, 6m 1119, YTD 356, 12m 1120) ; groups t7062 (2020-02 ->) ; SGS 7478 | t3065 | 2000-05 | monthly (mid-month) | Oct-2026 already out | % | Y t3065 v355 Oct-2026=0.32; SGS 7478 n=318 first 01/05/2000=0.09 last 01/10/2026=0.32 |
| INPC | SIDRA t1736 (index v2289, m/m v44, 3m 2290, 6m 2291, YTD 68, 12m 2292) ; SGS 188 | t1736 | 1979-03 | monthly | as IPCA | % | Y t1736 v44 Sep-2026=0.82; SGS 188 n=570 first 01/04/1979=3.45 last 01/09/2026=0.82 |
| IPCA core: trimmed mean with smoothing | SGS 4466 | 4466 | 1991-12 (data), CKAN says 1996-01 | monthly | month | % m/m | Y last 01/09/2026=0.31 |
| trimmed mean without smoothing | SGS 11426 | | 1991-01 | monthly | | % m/m | Y last 0.33 |
| core exclusion ex-0 (sem monitorados e alimentos no domicílio) | SGS 11427 | | 1991-01 | monthly | | % m/m | Y last 0.44 |
| core exclusion ex-2 | SGS 16121 | | 1991-01 | monthly | | % m/m | Y last 0.71 |
| core double weighting | SGS 16122 | | 1995-01 | monthly | | % m/m | Y last 0.37 |
| IPCA diffusion index | SGS 21379 | | 1991-01 (CKAN: 1999-08) | monthly | | % of items rising | Y last 54.91 |
| IPCA free prices / monitored / tradables / non-tradables | SGS 11428 / 4449 / 4447 / 4448 | | 1991-01 | monthly | | % m/m | Y last 0.55 / 1.59 / 0.20 / 0.80 |
| IPCA services / durables / semi-durables / non-durables | SGS 10844 / 10843 / 10842 / 10841 | | 1991-01 | monthly | | % m/m | Y 10844 last 0.61; 10841 last 0.69 (10842/10843 not fetched) |
| IGP-M % m/m | SGS 189 ; index IPEADATA `IGP12_IGPM12` | | SGS 1989-06 | monthly (month-end) | Oct-2026 out | % ; index Aug-94=100 | Y 189 last 01/10/2026=1.47 (repo note: Ipeadata index 1243.905) |
| IGP-DI % m/m | SGS 190 ; Ipeadata `IGP12_IGPDI12` | | SGS 1944-02 | monthly | Sep-2026 latest | % | Y 190 n=992 first 01/02/1944=1.45 last 01/09/2026=1.50 |
| IPA-DI index / INCC-DI index / IPC-Fipe m/m | IPEADATA (FGV, Fipe) | `IGP12_IPADI12` (IPA-DI index, ago-1994=100), `IGP12_INCC12` (INCC-DI index), `FIPE12_FIPE0001` (IPC-Fipe % m/m, São Paulo city); INCC-M `IGP12_INCCMG12`-style codes exist (decendial `IGP12_INCCMG1D12`) | 1944-01 (index) / 1939-02 (Fipe) | monthly | Sep-2026 (IPA/INCC), Sep-2026 (Fipe) | index / % | Y IPA-DI n=993 last 1391.632 (2026-09); INCC-DI last 1299.713 (2026-09); Fipe n=1052 first 1939-02=-1.52 last 2026-09=0.5079 |
| IPA-M, IPC-S, IPC-DI monthly | Ipeadata lists only annual `IGP_IPCG`, `IGP_IPADIG`; SGS CKAN has none | | | | | | N (not verified; Focus forecasts them, realized series not located) |

## 3. Activity
| series | source | code / URL | first | freq | lag | unit | verified |
|---|---|---|---|---|---|---|---|
| GDP quarterly, volume index (chained, 1995=100), NSA | SIDRA t1620 v583 (c11255/90707 = PIB a preços de mercado) | `/t/1620/n1/all/v/583/p/last/c11255/90707` | 1996Q1 | quarterly | 2026Q2 latest on 11-07 (~2 months) | index 1995=100 | Y 2026Q2 = 199.05 |
| GDP volume index, seasonally adjusted | SIDRA t1621 v584 | same pattern | 1996Q1 | quarterly | as above | index | meta Y (199601-202602), value N |
| GDP growth rates (q/q SA v6564, y/y v6561, 4Q accumulated v6562, YTD v6563) | SIDRA t5932 | `/t/5932/n1/all/v/6564/p/last/c11255/90707` | 1996Q1 | quarterly | as above | % | Y 2026Q2 q/q = 0.5 |
| GDP values, constant 1995 prices (NSA / SA) | SIDRA t6612 v9318 / t6613 v9319 | | 1996Q1 | quarterly | as above | R$ million | meta Y |
| IBC-Br NSA / seasonally adjusted | SGS 24363 / 24364 | | 2003-01 | monthly | Aug-2026 (~2 months) | index | Y 24363 last 01/08/2026=111.71919 ; 24364 last 110.40624 |
| IBC-Br components: agro 29601, industry 29603, services 29605, ex-agro 29607, taxes 29609 (SA: 29602/29604/29606/29608/29610) | SGS | | 2003-01 | monthly | Aug-2026 | index | Y 29601 last 109.95774, 29603 last 111.98530, 29605 last 111.65387; rest CKAN only |
| Industrial production (PIM-PF) | SIDRA t8888 (v12606 NSA idx 2022=100, v12607 SA, v11601 m/m SA, v11602 y/y, v11604 12m); old t3653 ended 2022-01 | `/t/8888/n1/all/v/12607/p/last/c544/129314` (c544/129314 = indústria geral) | 2002-01 | monthly | Sep-2026 already out (~5 weeks) | index 2022=100 | Y Sep-2026 SA = 102.13833 |
| Same via SGS | SGS 21859 / 21862 (name n/v; 2002-01 -> 2026-08 = 111.7 / 109.4, one month behind SIDRA) | | 2002-01 | monthly | Aug-2026 | index | fetch Y, name N |
| Retail (PMC) volume | SIDRA t8880 (v7169 NSA, v7170 SA, v11708 m/m, v11709 y/y; c11046/56734) | `/t/8880/n1/all/v/7170/p/last/c11046/56734` | 2000-01 | monthly | Aug-2026 (~2 months) | index 2022=100 | Y Aug-2026 SA = 108.68976 |
| Services (PMS) volume | SIDRA t5906 (v7167/7168; c11046/56726) | `/t/5906/n1/all/v/7168/p/last/c11046/56726` | 2011-01 | monthly | Aug-2026 | index 2022=100 | Y Aug-2026 SA = 110.51370 (adding c488 -> HTTP 400) |
| Unemployment PNAD Contínua, rolling quarter | SIDRA t6381 v4099; SGS 24369 (name n/v) | `/t/6381/n1/all/v/4099/p/last` | 2012-03 | monthly (rolling 3m) | jul-ago-set 2026 out | % labour force | Y t6381 JAS-2026 = 5.2; SGS 24369 n=175 first 01/03/2012=8.0 last 01/09/2026=5.2 |
| Calendar-quarter unemployment/underutilisation; headcounts | SIDRA t4099 (v4099, v4114, v4116) ; t6402 / t4093 | | 2012Q1 | quarterly | 2026Q2 | % ; thousand persons | meta Y |
| CAGED net jobs (Novo CAGED) | IPEADATA `CAGED12_SALDON12` (NSA) / `CAGED12_SALDONAJU12` (adjusted); `CAGED12_ADMISN12`, `CAGED12_DESLIGN12` | | 2020-01 | monthly | Aug-2026 | persons | Y n=80 first 2020-01=92678 last 2026-08=165827 (adjusted series returned the same last value) |
| Novo CAGED microdata (primary) | MTE FTP `ftp://ftp.mtps.gov.br/pdet/microdados/NOVO%20CAGED/<yyyy>/<yyyymm>/CAGEDMOV<yyyymm>.7z` (+CAGEDFOR, CAGEDEXC); legacy tree `/pdet/microdados/CAGED` | | 2020-01 | monthly | 202609 posted 2026-11-04 (~5 weeks) | 7z microdata | Y listing: CAGEDMOV202609.7z 49,478,375 B (NOT downloaded, > 5 MB cap); CAGEDFOR 1,056,240 B; MTE gov.br page `.../novo-caged` -> 404 |
| Consumer confidence | SGS 4393 ("Índice de Confiança do Consumidor", 1999-04) is identical in latest value to IPEADATA `FCESP12_IIC12` (Fecomércio-SP ICC, 1994-06): it is Fecomércio, not FGV | | 1999-04 / 1994-06 | monthly | Oct-2026 | index | Y both last 118.59 |
| FGV construction confidence | IPEADATA `FGV12_ICSTSA12` (NSA), `FGV12_ICSTCA12` (adj.), expectations `FGV12_IECSTSA12`, current `FGV12_ISACSTSA12` | | 2010-07 | monthly | Oct-2026 | index | Y ICSTSA n=196 first 116.2 last 89.8 |
| FGV industrial capacity utilisation (NUCI) | IPEADATA `CE12_CUTIND12`; SGS 1344 (name n/v, same history) | | 1970-01 | monthly | Oct-2026 (SGS 1344 only to 2026-07) | % | Y Ipeadata n=395 last 83.8; SGS 1344 last 82.9 |
| CNI ICEI (industry) / CNC ICEC (commerce) | IPEADATA `CNI12_ICEIGER12` (+`CNI12_ICEICA12`, `CNI12_ICEIEXP12`) / `CNC12_ICEC12` | | 2010-01 / 2013-01 | monthly | Oct-2026 / Sep-2026 | index | Y ICEI last 46.2; ICEC last 100.2 |
| FGV IBRE confidence suite (industry, services, commerce, ICE) | portalibre.fgv.br (HTTP 200; "Área do Cliente" login on pages) | | | | | | N: no free series route found; only the subsets above |
| PMI (S&P Global) | S&P Global | | | | | | N: commercial, not requested |

## 4. Fiscal
Sign convention (inferred, not read in docs today): NFSP series positive = deficit (5793 12m primary = -3.31 %GDP in 2002-11, +0.52 in 2026-09).
| series | source | code | first | freq | lag | unit | verified |
|---|---|---|---|---|---|---|---|
| Primary result, consolidated public sector, 12m % GDP | SGS | 5793 | 2002-11 | monthly | Sep-2026 (~5-6 weeks) | % GDP | Y last 0.52 |
| Primary result, monthly flow | SGS | 4649 | 2001-12 | monthly | Sep-2026 | R$ million | Y last 5496.60 |
| Nominal result 12m % GDP / monthly flow | SGS | 5727 / 4583 | 2002-11 / 2001-12 | monthly | Sep-2026 | % GDP / R$ million | Y 9.51 / 113,023.69 |
| Net public-sector debt (DLSP) % GDP / R$ million | SGS | 4513 / 4478 | 2001-12 | monthly | Sep-2026 | % GDP / R$ million | Y 69.98 / 9,379,279.09 |
| Net general-government debt % GDP | SGS | 4536 | 2002-01 | monthly | Sep-2026 | % GDP | Y 70.06 |
| Gross general-government debt (DBGG) % GDP, methodology since 2008 | SGS | 13762 | 2006-12 | monthly | Sep-2026 | % GDP | Y n=238 last 82.93 |
| DBGG old methodology (to 2007) | SGS | 4537 | 2002-01 | monthly | still returns values (95.24 in 2026-09) | % GDP | Y; not comparable, do not splice with 13762 |
| Tesouro Nacional result (RTN: revenue, transfers, expenditure, primary result, Governo Central) | Tesouro Transparente CKAN `resultado-do-tesouro-nacional` | XLSX resource `https://www.tesourotransparente.gov.br/ckan/dataset/ab56485b-9c40-4efb-8563-9ce3e1973c4b/resource/527ccdb1-3059-42f3-bf23-b5e3ab4c6dc6/download/` ; time-series API docs `https://apiapex.tesouro.gov.br/aria/v1/series-temporais/docs` (200; data endpoints not probed) | 1997-01 | monthly | LAST COLUMN 2026-07; file Last-Modified 2026-08-27 (stale ~2 months on 11-07) | R$ million current | Y downloaded (4,301,280 B, 27 sheets), read table 1.1 header cols 1997-01 -> 2026-07; ODbL |

## 5. External
| series | source | code / URL | first | freq | lag | unit | verified |
|---|---|---|---|---|---|---|---|
| Current account (BoP) | SGS | 22701 (receipts 22702, expenses 22703) | 1995-01 | monthly | Sep-2026 (~5 weeks) | US$ million | Y n=381 last -5099.7 |
| Current account 12m / % GDP | SGS | 24419 / 23079 | 1995-12 / 1995-01 | monthly | Sep-2026 | US$ million / % GDP | Y -59986.1 / -2.33 |
| Trade balance (BoP) | SGS | 22707 | 1995-01 | monthly | Sep-2026 | US$ million | Y last 6868.8 |
| FDI net / FDI in Brazil (IDP) | SGS | 22864 / 22885 | 1995-01 | monthly | Sep-2026 | US$ million | Y -7420.9 / 11294.5 |
| International reserves, cash / liquidity concept, daily | SGS | 13621 / 13982 (10-yr cap) | 1998-09 / 2008-01 | daily | D-2 (last 05/11/2026) | US$ million | Y 367,865 / 370,865 |
| International reserves, monthly | SGS | 3546 (name n/v) | 1971-01 | monthly | Oct-2026 | US$ million | Y n=670 last 365,019 |
| Real effective exchange rate | SGS 11752 (name n/v) | | 1988-01 | monthly | Aug-2026 | index | Y n=464 last 123.23. Ipeadata `GAC12_TCERM*` real effective series are INACTIVE (updated 2025-01) |
| PTAX USD daily | Olinda PTAX | `https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/CotacaoDolarDia(dataCotacao=@dataCotacao)?@dataCotacao='MM-DD-YYYY'&$format=json` | 1984 (repo note) | daily | same day | BRL/USD | Y 11-05-2026 venda 5.46210 compra 5.46150. SGS 1 is the "livre" venda (06/11/2026 = 5.5013), not PTAX |
| Trade by NCM/country (SECEX Comex Stat API) | `https://api-comexstat.mdic.gov.br/general?filter=<json>` GET, no auth (root `/` = 401 Bearer); typeForm 1 = exports | | 1997 per MDIC (n/v) | monthly | Sep-2026 on 11-07 | US$ FOB | Y exports 2026-01..09 monthly FOB, 2026-09 = 33,962,602,370 |
| Comex Stat bulk CSV `https://balanca.economia.gov.br/balanca/bd/comexstat-bd/ncm/EXP_2026.csv` | | | | | | | N: TLS `SEC_E_CERT_EXPIRED` (not bypassed); alternative = the API above |
| Brazil EMBI+ (country risk) | IPEADATA `JPM366_EMBI366` | | 1994-04-29 | daily | INACTIVE: last obs 2024-07-30 = 228 (series status I) | bp | Y n=7756 first 1120.0 last 228.0 |
| Brazil CDS 5y | none | | | | | | N: no free source found (Ipeadata and SGS names grepped: none) |

## 6. Credit and money
| series | source | code | first | freq | lag | unit | verified |
|---|---|---|---|---|---|---|---|
| Total credit outstanding | SGS | 20539 (first row = 0 in 1988: quirk), free resources 20542, % GDP 20622 | 1988-06 / 2007-03 / 1995-07 | monthly | Sep-2026 | R$ million / % GDP | Y 7,444,208 ; 4,187,437 ; 55.55 |
| Default rate (>90d) total / PJ / PF | SGS | 21082 / 21083 / 21084 | 2011-03 | monthly | Sep-2026 | % | Y 4.98 / 3.28 / 5.99 |
| Average lending rate, total | SGS | 20714 | 2011-03 | monthly | Sep-2026 | % a.a. | Y 32.36 |
| Average spread, non-revolving total / free-resources total | SGS | 27631 / 27634 | 2011-03 | monthly | Sep-2026 | pp | Y 15.20 / 26.10 |
| Household debt / 12m income; debt-service burden | SGS | 29037 / 29034 (ex-housing 29038, 29035) | 2005-01 / 2005-03 | monthly | Aug-2026 (~2 months) | % | Y 50.11 / 28.99 |
| Monetary base (restricted) | SGS | 1788 | 1946-02 | monthly | Sep-2026 | R$ thousand | Y 434,922,566 |
| M1 / M2 / M3 / M4 (end of period) | SGS | 27791 / 27810 / 27813 / 27815 (SA: 27841, 27842) | 2001-12 / 2001-08 (first value None) / 2001-08 / 2001-12 | monthly | Sep-2026 | R$ thousand | Y 654,222,301 / 7,870,395,191 / 14,246,711,983 / 16,048,649,973 |
| Credit by purpose/modality (~100 codes: 20594, 20606, 20590, ...) | SGS (CKAN titles) | | 2007-03 | monthly | | R$ million | listed only |

## 7. Expectations: BCB Focus (Olinda)
Base `https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/` (generic UA works, no auth). Service document lists exactly 13 entity sets; `ExpectativasMercadoInstituicoes` does not exist (HTTP 400), correcting the hedge in bcb_focus.md.
| entity set | content | first Data | verified sample (Data 2026-10-30) |
|---|---|---|---|
| ExpectativasMercadoAnuais | annual, by Indicador/DataReferencia (year), baseCalculo 0/1 | 2000-01-03 (repo note) | repo note |
| ExpectativaMercadoMensais | monthly (DataReferencia MM/YYYY) | 2000-01-03 | Y IPCA 10/2028 mean 0.3142, 91 resp. |
| ExpectativasMercadoTrimestrais | quarterly (4/2026) | 2001-11-06 | Y IPCA 4/2026 mean 1.2246 |
| ExpectativasMercadoSelic | Selic by Copom meeting (R1/YYYY .. R6/2028) | 2004-11-18 | Y R6/2028 mean 11.6210 median 11.5 (93 resp.) |
| ExpectativasMercadoInflacao12Meses / 24Meses | rolling next-12m/24m, `Suavizada` S/N | 2001-11-07 / 2021-03-31 | Y 12m IPCA mean 5.0031 |
| ExpectativasMercadoTop5Anuais / Mensais / Selic / Inflacao12Meses / Inflacao24Meses / ExpectativaMercadoTop5Trimestral | Top-5 forecasters, `tipoCalculo`, no respondents field | 2001-11-06 (Anuais, Mensais), 2004-11-18 (Selic) | Y Top5 annual IPCA 2026 mean 5.3347 |
| DatasReferencia | reference-period windows per Indicador | 2001-11 | Y first row IGP-M 11/2001 |
Lag: weekly (latest Data 2026-10-30 on 11-07). Always filter `Data ge` (whole IPCA = 10.5 MB per repo note).

## 8. Market context on B3 and rates
### 8a. Index levels, full daily history (free, official, unauthenticated JSON)
Route (found in repo note b3_index_portfolio.md, re-verified today): `GET https://sistemaswebb3-listados.b3.com.br/indexStatisticsProxy/IndexCall/GetPortfolioDay/<base64 of {"index":"<CODE>","language":"pt-br","year":"<YYYY>"}>` with a browser UA. One request = one calendar year as a month x day grid (`results[].day`, `rateValue1..12`, pt-BR strings `168.498,45`; plus `min`/`max` rows). Year before the index existed -> `results` null. About 9.5 KB per index-year; a full back-fill of the 23 indices below is roughly 400 requests at 1 req/s. Last obs on every index = 2026-11-06 (D-0/D-1: Saturday recon). The index is a PRICE index unless a TR variant exists (n/v: TR codes not tested). Base 1,000 at the first observation for the 2005+ thematic indices.
| index (B3 code) | name | first year / first obs verified | last 2026 | verified |
|---|---|---|---|---|
| IBOVESPA (alias IBOV also accepted) | Ibovespa | 1968-01-02 = 100.00 (1967 -> null); pre-1994 on old-currency scale | 2026-11-06 = 168,498.45 | Y |
| IBXX | IBrX 100 | 1994-12-29 = 1,092.52 (1993 empty) | 71,100.14 | Y |
| IBXL | IBrX 50 | 1997-12-30 = 1,000 | 28,554.13 | Y |
| SMLL | Small Cap | 2005-08-31 = 517.94 | 1,974.13 | Y |
| MLCX | Mid-Large Cap | 2005-08-31 = 396.98 | 3,519.22 | Y |
| IDIV | Dividendos | 2005-12-29 = 1,000 | 11,763.76 | Y |
| IFIX | Fundos Imobiliários | 2010-12-30 = 1,000 | 3,628.20 | Y |
| IFNC / ICON / IEEX / IMOB / IMAT / INDX / UTIL | Financeiro / Consumo / Energia Elétrica / Imobiliário / Materiais Básicos / Industrial / Utilidade Pública | 2004-12-30 / 2006-12-28 / 1994-01-03 / 2007-12-28 / 2005-12-29 / 1999-12-30 / 2005-12-29 | 17,026.42 / 2,588.31 / 121,610.51 / 1,128.17 / 6,206.41 / 29,877.41 / 17,410.17 | Y each |
| ISEE / ICO2 / IGCX / ITAG / IGNM / IGCT / IVBX2 / BDRX / IBRA | Sustentabilidade (ISE) / Carbono Eficiente / Governança Corp. / Tag Along / Novo Mercado / Gov. Trade / IVBX-2 / BDR / IBrA | 2005-11-30 / 2010-08-31 / 2001-06-25 / 2002-12-30 / 2006-12-28 / 2005-12-29 / 1999-12-30 / 2010-10-05 / 2005-12-29 | 3,908.55 / 2,899.71 / 26,045.84 / 36,412.00 / 4,367.12 / 7,508.35 / 17,100.31 / 28,037.58 / 6,603.30 | Y each |
Cross-check: IPEADATA `GM366_IBVSP366` (Ibovespa close, daily, source BM&FBovespa, 1993-04-27 = 24.5 -> 2026-11-05 = 166,192; n=8,335) agrees in scale with B3 (B3 has 11-06 = 168,498.45, one day further). Ipeadata also has `GM366_IBVSPV366` (volatility) and `GM12_IBVSP12` (monthly % via ANBIMA).

### 8b. Other index/curve context
| series | source | code / URL | first | freq | lag | unit | verified |
|---|---|---|---|---|---|---|---|
| IMA family (IMA-B, IMA-B 5, IMA-B 5+, IMA-S, IMA-Geral, IMA-Geral ex-C, IRF-M, IRF-M 1, IRF-M 1+): index level, daily/monthly/YTD/12m/24m var, duration, yield | ANBIMA free XML (latest day only) | `https://www.anbima.com.br/informacoes/ima/arqs/ima_completo.xml` (88,673 B, ISO-8859-1, attribute `T_Num_Indice` per `FAMILIA`) | none (snapshot) | daily | 06/11/2026 on 11-07 | index (Dec-2000 = 1000, per ANBIMA convention n/v) | Y IMA-B 12,005.950907 (var dia 0,4376); IMA-B 5+ 13,024.470749; IMA-S 9,109.224019; IRF-M 23,445.456968. EPHEMERAL: no history route found; the `ima-sh.asp` page is a 2016 notice. Archive daily; IMA-S history can be rebuilt from CDI (SGS 12) and IMA-B/IRF-M only from the day archiving starts (history route N, not verified) |
| DI x pré curve (B3 TS), 22 curve ids (PRE, DIC, DIM, TR, DOL, ...) | B3 referenceRatesProxy | repo note b3_reference_rates.md (re-verified: `GetList` id PRE, 282 vertices, date 2026-11-06) | 2000-01-14 via pesquisapregao TS files | daily | same day | % a.a. (252 d) | Y PRE 1d = 13.65 ; 4y (1008 d) PRE = 14.90 |
| DI1 futures curve | pyield mirror 2018+ / B3 TS 2000+ | repo notes | | | | | not re-probed (known) |
| Implied inflation (breakeven) | derived: (1+PRE)/(1+DIC)-1 at the same 252-day vertex, PRE = "DI x pré", DIC = "DI x IPCA" | two `GetList` calls (pageSize <= 100; pageSize 400 returned an empty result) | 2000 (TS files) | daily | same day | % a.a. | Y 2026-11-06 at 1008 d: PRE 14.90, DIC 7.62 -> breakeven 6.77 %. Caution: at the 1-day vertex DIC = 13.65 = PRE (not a real rate), short real vertices (5-9 d: 4.44-7.17) are noise; use vertices >= 6 months only |
| Country risk EMBI+ Brazil | IPEADATA `JPM366_EMBI366` | | 1994-04-29 | daily | DEAD: last obs 2024-07-30 = 228 bp | bp | Y (see S5) |
| Country risk CDS | none | | | | | | N |
| Investor flow: B3 "Participação dos investidores" (Institucionais, Instituições Financeiras, Investidor Estrangeiro, Investidores Individuais, Outros; buy and sell volume and %, MONTH-TO-DATE cumulative) | B3 BDI table `SharesInvesVolum` | `POST https://arquivos.b3.com.br/bdi/table/SharesInvesVolum/<d>/<d>/1/100` body `{}`; latest day `GET /bdi/table/workday` | none (window D-21) | daily (cumulative since month start) | 2026-11-06 on 11-07 | R$ (values like 55,480,108 buy, 31.79 %, 57,538,314 sell, 32.97 %: unit not in the response I read; BDI column text n/v) | Y 2026-11-06 foreign: buys 55,480,108 (31.79 %), sells 57,538,314 (32.97 %); 2026-10-07 served, 2026-10-06 empty = 21-business-day window, EPHEMERAL. Daily flow = difference of consecutive MTD values (reset each month) |
| Investor participation, monthly | B3 BDI table `SharesInvesVolumMonthly` | same pattern | | monthly | | | N: empty for 2024-06, 2026-09, 2026-10 (all date forms tried: month range and last day) |
| Long investor-flow history (foreign flow by day, 2000s ->) | not found on B3 free routes; B3 "Segmentação de Investidores" is a commercial/API product page | | | | | | N (history route not found; archive SharesInvesVolum daily from now) |

## 9. Agriculture, commodities, fuel
CEPEA/ESALQ (USP): data licence printed on every indicator page = CC BY-NC 4.0 (non-commercial, attribution: fine for personal research). The series pages `https://www.cepea.org.br/br/indicador/series/<slug>.aspx?id=<n>` return the COMPLETE history as an `.xls` attachment (`application/vnd.ms-excel`) with no login: one request each, 94-558 KB. The file is an OLE workbook that `xlrd` reads only with `ignore_workbook_corruption=True` (Workbook corruption error otherwise). Columns `Data` (dd/mm/yyyy), `À vista R$`, `À vista US$` (boi: `A prazo`). Lag: last row 06/11/2026 on Saturday 07/11 (D-0/D-1). The database-consultation page `https://www.cepea.org.br/br/consultas-ao-banco-de-dados-do-site.aspx` answered HTTP 403 and was not retried (stopped per rule; not needed).
| series | source | code / URL | first | freq | lag | unit | verified |
|---|---|---|---|---|---|---|---|
| Soja Paranaguá | CEPEA | `series/soja.aspx?id=12` (id=92 not fetched: second soy series on the page) | 1997-07-29 | daily | D-1 | R$/saca 60 kg; US$ | Y 7,297 rows, last 06/11/2026 = 152.10 R$ / 27.62 US$ |
| Milho ESALQ/B3 | CEPEA | `series/milho.aspx?id=77` | 2004-08-02 | daily | D-1 | R$/saca 60 kg | Y 5,546 rows, last 66.77 / 12.12 |
| Boi gordo (indicador à vista) / média a prazo SP | CEPEA | `series/boi-gordo.aspx?id=2` / `id=1` | 1997-07-23 | daily | D-1 | R$/arroba 15 kg | Y 7,288 rows; id=2 last 392.70 R$ / 71.31 US$; id=1 last 396.91 |
| Café arábica / robusta | CEPEA | `series/cafe.aspx?id=23` / `id=24` | 1996-09-02 / 2001-06-06 (first rows 0.0) | daily | D-1 | R$/saca 60 kg | Y 7,516 / 6,288 rows; last 1,611.14 / 977.34 R$ |
| Açúcar cristal branco SP / cristal Santos FOB | CEPEA | `series/acucar.aspx?id=53` / `id=308` | 2003-05-20 / 2020-01-02 | daily | D-1 | R$/saca 50 kg | Y 5,824 / 1,707 rows; last 129.58 / 133.17 R$ |
| Etanol hidratado combustível SP / anidro / hidratado outros fins | CEPEA | `series/etanol.aspx?id=103` / `id=104` / `id=85` | 2002-11-29 / 2002-11-29 / 2002-01-01 (first row 0.0) | weekly (Fridays) | D-1 | R$/litro (n/v in file) | Y 1,250 / 1,250 / 1,211 rows; last 2.8799 / 3.5831 / 2.8339 |
| Fuel retail prices (gasoline, ethanol, diesel, GNV, GLP; Brasil/regions/states/municipalities) | ANP "Série histórica do levantamento de preços" | monthly Brasil: `https://www.gov.br/anp/pt-br/assuntos/precos-e-defesa-da-concorrencia/precos/precos-revenda-e-de-distribuicao-combustiveis/shlp/mensal/mensal-brasil-desde-jan2013.xlsx` (113,245 B; HEAD -> 403, GET/Range works); 2001-2012 monthly/weekly files under `shlp/2001-2012/`; page `.../serie-historica-do-levantamento-de-precos` | 2013-01 (monthly), 2001-2012 files separate | monthly (weekly files exist: not verified for 2013+) | Sep-2026 last row (46266 = 2026-09-01; ~5 weeks) | R$/l (R$/13 kg for GLP n/v) | Y downloaded, 1,073 rows; last rows `OLEO DIESEL 6.70 R$/l (8,180 stations)`, `OLEO DIESEL S10 7.16 R$/l (13,682 stations)`; columns beyond the first 10 not decoded |
| Brent / oil price | not probed in this session (Ipeadata has ANP production/consumption and `ANP_PRGASOL` annual prices; no Brent code was grepped) | | | | | | N |
| Other agricultural prices | IPEADATA state-level monthly (e.g. `DEPAE12_ATMI12` corn SP wholesale 60 kg, Conab/IE; `DERAL12_PRBGO12` boi gordo PR) | | | monthly | Sep/Oct-2026 | R$ | listed (names + last update only) |

## 10. Gaps and findings (2026-11-07)
- Paid or absent (free route not found): PMI (S&P), FGV IBRE confidence suite (login portal), CDS, long B3 investor-flow history, IMA history, IPA-M/IPC-S monthly realized, Copom future calendar/atas route (guessed bcb.gov.br API paths failed), Brent (not probed).
- Dead/stale: EMBI+ Ipeadata (ends 2024-07-30); Ipeadata real effective FX GAC12_TCERM* (2025-01); Tesouro RTN XLSX (data to 2026-07, file dated 2026-08-27); SGS 1344 stops 2026-07 vs Ipeadata Oct; balanca.economia.gov.br TLS cert expired.
- Ephemeral, archive daily: IMA XML, B3 SharesInvesVolum (D-21), plus repo-known ANBIMA/BDI.
- Corrections to repo notes: Focus has no Instituições entity set; SGS 432 carries future-dated rows; SGS 4393 is Fecomércio not FGV; SGS metadata page (www3.bcb.gov.br/sgspub) rejects curl and browser UA (502 "Requisição inválida"), so names for 433, 188-190, 7478, 226, 24369, 21859, 21862, 1344, 3546, 11752 are not verified (CKAN catalogue `ckan_sgs.json` lacks them).
- Total download this session ~20 MB (largest: Ipeadata metadata 8 MB in 5 pages, CKAN SGS catalogue 5 MB in 5 pages, CEPEA 10 XLS 3.6 MB, Tesouro RTN 4.3 MB). Rate <= 1 req/s per host; no logins, no CAPTCHA, one HTTP 403 (CEPEA consult page) not retried.

## Focus parsed (2026-11-07, `ingest/focus.py`)
- All 8 Olinda tables into one staging table `expectation`: 3,605,401 rows 2000→2026 from 724 MB of JSON (27 MB
  staged). Reference column by table: `DataReferencia` (annual `2026`, monthly `12/2026`, quarterly `1/2024`),
  `Reuniao` (`R8/2027`), none for the 12/24-month inflation tables (stored as `12m`/`24m`).
- The Top-5 tables use lower-case keys (`indicador`, `media`, `coeficienteVariacao`); the others capitalised ones.
- 1,897 Top-5 rows carry no statistic at all (IGP-DI, IGP-M, IPCA, Selic, mostly 2010-2016): quarantined.
- The survey of a Friday is served from the following Monday (2026-11-06 empty on 2026-11-07; 2026-10-30 served).

## Copom parsed (2026-11-07, `ingest/copom.py`)
- 290 decisions, meeting 1 (1996-06-26) to 282 (2026-11-04), one row per decision with its validity period. Meeting
  33 (1999) has three rows: the later two are the president's use of the bias (`UsoMetaSelic` true).
- `MetaSelic` is the Selic target in % a.a. from 1999-03-05. Before, the field holds the TBC (19-29 in 1998, 1.9 in
  1996): its unit is not stated *(not verified)*; SGS 432 is the target series from 1999.
