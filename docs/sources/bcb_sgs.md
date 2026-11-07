# bcb_sgs — Banco Central do Brasil: SGS time-series API

**Tier:** P. **Recon date:** 2026-11-07 (partial; stopped early by the coordinator). **Fixture:** `tests/fixtures/bcb_sgs/` (CDI series 12, 2024-Q1 and 2024-01..2025-01-10; calculator factors).

Every statement below was measured on the recon date against a real response, unless marked *(not verified)*.

## 1. Access
- `https://api.bcb.gov.br/dados/serie/bcdata.sgs.<code>/dados?formato=json&dataInicial=dd/mm/aaaa&dataFinal=dd/mm/aaaa`; `/dados/ultimos/N?formato=json`. No auth. Browser UA used; generic UA not tested.
- `formato=csv` works (`"data";"valor"`, `;`-separated, quoted, pt-BR decimal comma); `formato=xml` → 400 `{"erro":"Formato invalido. Use json, csv, application/json ou text/csv."}`.
- **Window cap, daily series: 10 years, inclusive.** 01/01/2015–01/01/2025 → 200; 01/01/2015–02/01/2025 → **HTTP 406** `{"error":"O sistema aceita uma janela de consulta de, no máximo, 10 anos em séries de periodicidade diária","message":…,"syntax":…}`. No dates at all on a daily series → same 406. Monthly series (433, 189) return full history with no dates (433: 20,880 B from 01/01/1980; 189 from 01/06/1989).
- **Metadata:** no `/metadados` endpoint (404 `endpoint not found!`). Names/units/frequency/start are in BCB CKAN: `https://dadosabertos.bcb.gov.br/api/3/action/package_search?fq=codigo_sgs:<code>` (fields `title`, `periodicidade`, `unidade_medida`, `inicio_periodo`, `codigo_sgs`, licence ODbL). Legacy SOAP WSDL `https://www3.bcb.gov.br/wssgs/services/FachadaWSSGS?wsdl` answers 200 (not explored).

## 2. Datasets (codes confirmed by fetch; names from CKAN)
| code | name (CKAN) | unit | sample (date: value) |
|---|---|---|---|
| 12 | CDI daily *(CKAN fq returned nothing for 12)* | % a.d., 6 dp | 02/01/2024: 0.043739; first 06/03/1986 |
| 4389 | CDI annualised base 252 *(CKAN returned nothing)* | % a.a., 2 dp | 02/01/2024: 11.65 |
| 11 | Taxa de juros – Selic | % a.d. | 02/01/2024: 0.043739; from 04-06-1986 |
| 1178 | Selic anualizada base 252 | % a.a. | 11.65 |
| 432 | Meta Selic definida pelo Copom | % a.a. | 13.75 (from 1999-03-05) |
| 226 | TR *(name not verified)* | % per period | has `dataFim` (period start→+1 month): 01/01/2024→01/02/2024: 0.0875 |
| 195 | Poupança a partir de 04.05.2012 – rentab. no período | % a.m. | has `dataFim`; 0.5879 |
| 25 | Poupança até 03.05.2012 – rentab. no período | % a.m. | identical to 195 in Jan 2024 (Selic > 8.5%); difference when Selic ≤ 8.5% not verified |
| 433 | IPCA monthly % *(name not verified)* | % a.m., 2 dp | date = 01/mm/aaaa |
| 189 | IGP-M monthly % *(name not verified)* | % a.m., 2 dp | 01/10/2026: 1.47 |
| 1 / 10813 | Dólar livre venda / compra (PTAX) | BRL/USD, 4 dp | 02/01/2024: 4.8916 |
No CDI accumulated-factor series was found (not searched beyond the above).

## 3. Layout
- JSON array of `{"data":"dd/mm/aaaa","valor":"<decimal string, '.' separator>"}`; period series add `"dataFim"`. Values are strings.
- Verbatim: `[{"data":"02/01/2024","valor":"0.043739"},{"data":"03/01/2024","valor":"0.043739"},…`

## 4. Quirks
- **CDI rounding (measured):** series 12 = round_half((1 + s4389/100)^(1/252) − 1, 6 dp in %), i.e. the daily factor to 8 dp. 0 mismatches on 5,021 days (2000–2009, 2016-11-07..2026-11-05); truncation mismatches 2,112. No exact ties, so half-up vs half-even undistinguished.
- **Accumulated factor (BCB Calculadora do Cidadão):** start inclusive, end exclusive, 8 dp; reproduced exactly (see fixture README).
- **Lag:** on 2026-11-07, series 11 had 06/11/2026, series 12 only 05/11/2026.
- **Future dates:** 432 `/ultimos/4` returned dates up to 09/12/2026 (target forward-filled past today).
- **Unconditional HTTP 304** with empty body on `/ultimos/3` for 432 and 4389 (no conditional headers sent; also with `Cache-Control: no-cache`); `/ultimos/4` or a date-range request returns 200. A connector must treat 304-without-cache as a retry with another form.
- `/ultimos/N` order is not guaranteed: 195 came newest-first, others oldest-first. Sort by date.
- Error example `syntax` text is self-inconsistent (suggests a >10 y window); ignore it.

## 5. Identity fields
- SGS code is the series identity (`series_definition.source_code`).

## 6. Ephemerality
- Full history available (within 10-year windows for daily series). No vintages: revisions overwrite (not verified directly); store kt timestamps.

## 7. Open questions
- Names/units for 12, 4389, 226, 433, 189 (CKAN fq returned none; try `q=`).
- 25 vs 195 divergence period; TR `dataFim` semantics on month ends.
- B3/CETIP published "Índice DI" as a second accumulated-factor check (not fetched).
- Rate limit behaviour (none hit at ~1 req/s).
