# anbima_projecoes — ANBIMA: IPCA / IGP-M projections (Comitê de Acompanhamento Macroeconômico)

**Tier:** P. **Recon date:** 2026-11-07. **Fixture:** none (values quoted below only).

## 1. Access
- No stand-alone free projections page/file found: `/informacoes/projecoes/`, `/informacoes/projecoes-inflacao/` and `/pt_br/informar/estatisticas/precos-e-indices/projecoes.htm` → 404.
- Free carriers: (a) **Quadro Indicadores** `https://www.anbima.com.br/informacoes/indicadores/` (200; "Data e Hora da Última Atualização: 06/11/2026 - 18:18 h"; HTML table + `Indicadores.xls` link, not downloaded): IGP-M (out/26) **number index 1.243,905**, var 1,47 %; IGP-M projection (nov/26) **0,87**; IPCA (set/26) index 7.695,82 (= SIDRA), var 0,82; IPCA projection (out/26) **0,21**; also Selic estimate, DI-B3, USD/EUR, TR, TBF. Sources cited: FGV (IGP-M), IBGE (IPCA). (b) the `Ref=P` rows of the VNA file (anbima_vna). Methodology: `.../informacoes/vna/metodologia_projecoes.asp` (200: projections collected on the IGP-M/IPCA release day, ≥ 50 % of the sample; for IGP-M previews, current and next month).
- Paid: ANBIMA Feed package "Projeções IPCA e IGP-M" *(from feed.anbima.com.br)*.

## 2. Datasets
| dataset_id | granularity | history | cadence |
|---|---|---|---|
| quadro_indicadores | latest values only | **none (single snapshot)** | daily; projections change on release days |

## 3–5. Layout / quirks / identity
Not parsed (HTML table; xls not fetched) *(not verified)*.

## 6. Ephemerality
**EPHEMERAL, single snapshot.** The Quadro is the only free source of the IGP-M **number index** (FGV) found so far (BCB SGS has IGP-M % only): archive at least on every IGP-M release, with the xls. Free long-history proxy for expected inflation: BCB Focus (bcb_focus), not identical to ANBIMA's committee.

## 6b. History routes measured 2026-11-08
The "Quadro Indicadores" page has no date form (`default.asp` posts nothing historical; `arqs/indicadores.xls` and `Estimativa_SELIC_ANBIMA.pdf` are latest only). Internet Archive CDX lists 47 daily captures of `anbima.com.br/indicadores/indicadores.asp` (2012-12-15 → 2019-09-17: 1 in 2012, 1 in 2013, 3 in 2014, 5 in 2015, 5 in 2016, 9 in 2017, 14 in 2018, 9 in 2019; the xls: 5 in 2014-17) and 7 of the current path (2018-2026). Replay with `id_` returned real pages (2017-07-21: IPCA jun/17 index 4.832,27, projection jul/17 0,10) but **HTTP 429 after ~5 requests at 1.5 s**: not archived; a sparse best-effort backfill (about 47 days of IPCA/IGP-M projections) needs a slower, resumable fetch and a parser for the 2012-19 layouts *(not done)*.

## 7. Open questions
- Fetch and parse `Indicadores.xls`; whether ANBIMA Data exposes projection history (token needed).

## 8. Parsed (staging, `ingest/anbima_parsers.py`, 2026-11-07)
Layout confirmed on the archived page (fixture `tests/fixtures/anbima_projecoes/`): ISO-8859-1 XHTML; the stamp "Última Atualização: dd/mm/aaaa - hh:mm h" is `updated_at`; tall table `indicator`: selic_estimate, selic_bcb, di_b3, igpm/ipca `_index`, `_var_month`, `_projection` (with the reference month, e.g. `out/26`, `nov/26`), usd/eur buy/sell (BRL), tr, tbf, fds_quota. An unknown row label raises (layout change is loud). The USD sell 5.5013 of 2026-11-06 equals the PTAX close. Reparse: 17 rows, 0 quarantined. `Indicadores.xls` still not fetched.
