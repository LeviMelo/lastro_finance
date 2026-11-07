# ibge_sidra — IBGE: SIDRA API (IPCA, IPCA-15 index numbers)

**Tier:** P. **Recon date:** 2026-11-07. **Fixture:** `tests/fixtures/ibge_sidra/` (IPCA index full history + last 12, all variables of the last month, IPCA-15 last 3, table metadata; ~190 KB).

## 1. Access
- `https://apisidra.ibge.gov.br/values/t/<table>/n1/all/v/<var>/p/<period>` → 200 JSON, no auth, browser UA. Metadata: `https://servicodados.ibge.gov.br/api/v3/agregados/<table>/metadados` → 200. 1 req/s.
- **Confirmed:** table 1737, variable **2266** = "IPCA - Número-índice (base: dezembro de 1993 = 100)", unit "Número-índice" (MC 30). Last point 2026-09 = **7695.82**. Same table: v63 monthly % (0.82), 2263 3-month, 2264 6-month, 69 year-to-date, 2265 12-month (4.58). Table 1737 title: "IPCA - Série histórica com número-índice, variação mensal e variações acumuladas…"; frequency monthly, **197912 → 202609**, only territorial level N1 (Brasil).
- **IPCA-15:** table 3065 (from 200005 → 202610), variable **1117** = "IPCA15 - Número-índice (base: dezembro de 1993 = 100)": 2026-08 7490.51, 09 7542.94, 10 7567.08; v355 monthly %, 1118/1119/356/1120 accumulations. (Table 1705 is the old IPCA-15 items table, 2012-02…2020-01, not the index.)

## 2. Datasets
| dataset_id | granularity | history | cadence |
|---|---|---|---|
| t1737_v2266 IPCA index | monthly, Brasil | 1979-12 → 2026-09 (562 rows) | monthly, ~10th of next month *(from docs)* (Oct 2026 not yet out on 11-07; IPCA-15 for 2026-10 already is) |
| t3065_v1117 IPCA-15 index | monthly | 2000-05 → 2026-10 | monthly, mid-month |

## 3. Layout
JSON array; **element 0 is a header row** (field-label dictionary) — drop it. Fields: `NC/NN` territorial level, `MC/MN` unit, `V` value (string), `D1C/D1N` Brasil, `D2C/D2N` variable, `D3C/D3N` period.
```
{"NC":"1","NN":"Brasil","MC":"30","MN":"Número-índice","V":"7695.8200000000000","D1C":"1","D1N":"Brasil","D2C":"2266","D2N":"IPCA - Número-índice (base: dezembro de 1993 = 100)","D3C":"202609","D3N":"setembro 2026"}
```

## 4. Quirks
- `V` is a string with **13 decimals** (`7695.8200000000000`); index published with 2 dp since the recent decades; the first rows are rebased fractions of the pre-Real currencies: 1979-12 = `0.0000000076183`, 1980-01 = `0.0000000081223` → keep as Decimal string, never float.
- **Period code** `YYYYMM` (`202609`), `D3N` pt-BR text "setembro 2026" (not for parsing). `p/last 12` URL-encoded `last%2012`; `p/all`, `p/202601-202609` forms exist *(range form not tested)*.
- Monthly series: store the period, not a fake date. Revisions: IPCA is not revised; not tested beyond that *(from docs)*.
- **IGP-M is FGV, not IBGE.** BCB SGS 189 is the monthly **% change only** (01/10/2026 = 1.47). No SGS number-index series for IGP-M was found: CKAN `package_search` for IGP-M/IGP-DI returns only debt-composition series (4175, 10647, 4176); SGS 190 = IGP-DI %, 7447/7450 other % series (names not verified). IGP-M index numbers come from FGV IBRE ("FGV Dados", `https://extra-ibre.fgv.br/IBRE/sitefgvdados/consulta.aspx` → 200, 5.9 KB, series export/login not examined; `portalibre.fgv.br/igp-m` → 404, `/indices-de-precos` → 200). Free latest-only source: ANBIMA Quadro Indicadores (see anbima_projecoes): IGP-M (out/26) number index 1.243,905, FGV-sourced, snapshot only, archive each release. Fallback: chain the index from SGS 189 % (2 dp rounding error accumulates; to cross-check against ANBIMA/Tesouro VNA for NTN-C) *(not verified numerically)*.

## 5. Identity fields
IBGE table + variable ids (`t1737/v2266`) → series_id; period `YYYYMM`.

## 6. Ephemerality
Not ephemeral: full history on request. Keep kt = fetch timestamp.

## 7. Open questions
- Exact release hour; FGV IGP-M index route (open data? ANBIMA VNA files carry projected/realised IGP-M index?).
