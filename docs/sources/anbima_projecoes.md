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

## 7. Open questions
- Fetch and parse `Indicadores.xls`; whether ANBIMA Data exposes projection history (token needed).
