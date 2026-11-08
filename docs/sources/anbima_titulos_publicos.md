# anbima_titulos_publicos — ANBIMA: secondary market of federal bonds (taxas indicativas)

**Tier:** P. **Recon date:** 2026-11-07. **Fixture:** `tests/fixtures/anbima_titulos_publicos/` (all 6 daily txt files served on that day + 1 xls).

## 1. Access
- Free, no auth, generic UA works. Form page `https://www.anbima.com.br/informacoes/merc-sec/` (states "Podem ser consultados os valores referentes aos últimos cinco dias úteis";
  JS alert "Histórico disponível de 5 dias úteis"; hidden `Dt_Ref_Ver=20261029` = earliest date).
- Files: `https://www.anbima.com.br/informacoes/merc-sec/arqs/msYYMMDD.txt` (**YYMMDD**, not DDMMYY — e.g. `ms261106.txt`).
  Spreadsheet `arqs/mYYmonDD.xls` with **pt-BR month** (`m26nov06.xls`, `m26out29.xls`). `arqs/Msec_txt.txt` = latest day (byte-identical to ms261106).
- HTML: `resultados/msec_DDmonYYYY_{ltn,ntn-b,ntn-c,ntn-f,lft}.asp` (pt month, e.g. `msec_29out2026_ltn.asp`), GET works.
- Measured window on 2026-11-07: ms261029…ms261106 = 200 (6 business days; 02/11 holiday); ms261028, 261027, 261023, 261001, 260901, 260102, 250102, 240102, 200102, 160118, 100104 = 404 (IIS 404 page, 1245 bytes). Same for xls and asp of 28/10.
- Page notice dated 2026-03-10: delays in publication due to B3 operational issues.

## 2. Datasets
| dataset_id | granularity | history depth | cadence | URL pattern |
|---|---|---|---|---|
| ms_txt | bond × day | **rolling ~6 business days** | daily (D0 evening, exact time not verified) | `arqs/msYYMMDD.txt` |
| ms_xls | same, Excel | same | daily | `arqs/mYYmonDD.xls` |

## 3. Layout (txt, confirmed on fixture)
- Latin-1, CRLF. Line 1 title, line 2 blank, line 3 header, `@`-separated:
  `Titulo@Data Referencia@Codigo SELIC@Data Base/Emissao@Data Vencimento@Tx. Compra@Tx. Venda@Tx. Indicativas@PU@Desvio padrao@Interv. Ind. Inf. (D0)@Interv. Ind. Sup. (D0)@Interv. Ind. Inf. (D+1)@Interv. Ind. Sup. (D+1)@Criterio`
- Sample: `LTN@20261106@100000@20250110@20270401@13,77@13,7242@13,7549@951,116782@0,00558174106619@13,6004@14,0343@13,5771@14,0069@Calculado`
- Dates YYYYMMDD; decimals comma; rates % a.a. base 252. Layout of the xls *(not verified)*.

## 4. Quirks
- Since 2018-01-18 buy/sell firm average rates replaced min/max (page notice). Retifications are published in place (page lists past corrections) → re-fetch the window daily and keep every sha256 version.

## 5. Identity fields
`Codigo SELIC` + `Data Vencimento` (+ `Titulo`) → Tesouro instrument; ISIN not present.

## 6. Ephemerality
**EPHEMERAL.** Only ~6 business days are served; everything older is 404. Archive daily from now on (fetch whole window each day to catch retifications). Older history: Tesouro Transparente (own rates, not ANBIMA) or paid ANBIMA Data/Feed *(not verified)*.

## 7. Open questions
- Publication time of day; see §8 for history routes (ANBIMA Data needs a token; Wayback replay to be retried).

## 8. Long-history routes tried (2026-11-07)
| route | result |
|---|---|
| Server window of the form files (txt/xls/asp, ETTJ, VNA, debentures) | all four ANBIMA free forms: 6 business days (29/10..06/11/2026); enforced server-side (POST/GET of older dates returns 404 or a stub). |
| ANBIMA Data `https://data.anbima.com.br/` (Next.js SPA, 200) | page JS reveals the backend `https://data-api.prd.anbima.com.br/web-bff/v1/{titulos-publicos,debentures,certificado-recebiveis,fidc,feriados/periodo}` and `/v2/fundos`; unauthenticated GET → **401 `{"msg":"token cannot be blank"}`** (titulos-publicos?view=precos, debentures, feriados). Token comes from the app's Firebase sign-in: **not attempted (no login)**. The app itself shows "Quer acesso ao histórico completo de preços da ANBIMA?" linking to ANBIMA Feed. Credentials embedded in the public JS were not used. Whether the logged-in free tier gives history: *(not verified)*. |
| ANBIMA Feed `https://feed.anbima.com.br/` (200) | paid API (Títulos Públicos package listed at R$ 686,50 fixed monthly fee *(from page)*; free to ANBIMA associates; sandbox exists); covers VNA, curvas, intradiário, projeções, debêntures, índices. Full-history terms *(not verified)*. |
| Internet Archive CDX, new path `/informacoes/merc-sec/arqs/*` | only 5 distinct 200 files: ms260925, ms260928, ms260929, ms261023, ms261026 (captured 2026-10-01 and 2026-10-28, i.e. recent ad-hoc captures; ms260925 replay returned a real file, 6,684 B). 404 captures of ms210326/ms220602 (2022-23). |
| Internet Archive CDX, old path `/merc_sec/arqs/*` (host `anbima.com.br:80`) | 135 distinct 200 URLs: **85 distinct daily dates, 2012-05-30 → 2018-11-07** (txt 85, xls 46; per year 2012:5, 2013:8, 2014:6, 2015:29, 2016:28, 2017:8, 2018:1) out of ~1,600 business days → ~5 % coverage, irregular. Content not verified: replay (`web/<ts>id_/…`) of 2015 captures returned **HTTP 429 "suspected abusive bot traffic"** on 3 attempts (10–15 s apart, two URL variants) while CDX queries and a 2026 replay worked. Worth retrying later, politely (one request per several seconds), before concluding. |
| Tesouro Transparente | own Tesouro Direto morning rates/PUs 2004-12-31 → today: the free long-history substitute (not ANBIMA secondary-market indicative rates). |
| B3 reference rates / BCB | curves (DI x pré) from B3 for the pré curve; not ANBIMA. |

**Implication:** ANBIMA indicative rates, ETTJ, VNA and debenture rates have **no free systematic history**: LASTRO must archive all four daily from now on (≈ 180 KB + 3 KB + 1 KB + 3 KB per day), and treat 2012–2018 Wayback files as a sparse best-effort backfill.

## 8b. Parsed (staging, `ingest/anbima_parsers.py`, 2026-11-07)
`bond_rate` from `ms_txt` only (the `.xls` twin is archived, not parsed): 15 fields, dates YYYYMMDD, rates % a.a. (LFT: spread over Selic), `price_brl` = PU. `Desvio padrao` has no stated unit (kept as published). 50 rows a day; reparse 300 rows (6 days), 0 quarantined.
