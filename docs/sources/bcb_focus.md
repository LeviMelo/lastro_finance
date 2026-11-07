# bcb_focus — Banco Central do Brasil: Focus market expectations (Olinda)

**Tier:** P. **Recon date:** 2026-11-07. **Fixture:** `tests/fixtures/bcb_focus/` (IPCA annual for 2026-10-30 and 2000-01-03, Selic top 2, CSV sample).

## 1. Access
- `https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/<EntitySet>?$format=json&$filter=…&$orderby=…&$top=…` ; `$metadata` 200. No auth, browser UA, no failures.
- Filter dates are ISO strings: `$filter=Indicador eq 'IPCA' and Data eq '2026-10-30'`; `Data ge '2020-01-01'` works. `$skip`, `$orderby`, `$top`, `$format=text/csv` all work. **No row cap seen:** unfiltered `ExpectativasMercadoAnuais` returned 1,069,133 rows in one 247 MB response (do not do that); IPCA only = 48,782 rows, 10.5 MB. `$top=1000000` gives the same count as no `$top`.

## 2. Datasets (entity sets from $metadata)
`ExpectativasMercadoAnuais` (fields Indicador, IndicadorDetalhe, Data, DataReferencia, Media, Mediana, DesvioPadrao, Minimo, Maximo, numeroRespondentes, baseCalculo), `ExpectativaMercadoMensais` (DataReferencia `MM/YYYY`), `ExpectativasMercadoTrimestrais`, `ExpectativasMercadoSelic` (Reuniao `R6/2028`), `ExpectativasMercadoInflacao12Meses`, `…24Meses`, the `…Top5…` variants (+ `tipoCalculo`), `DatasReferencia` (Indicador, periodo, DataReferencia1/2), instituições entity (`ExpectativasMercadoInstituicoes`, in the type list, not in the entity-set list *(not verified)*).
- Anuais measured: Indicador values (34, accents as UTF-8): IPCA, IGP-M, IGP-DI, IPCA-15, INPC, IPC-Fipe, IPA-DI, IPA-M, IPCA Administrados/Livres/Serviços/Bens industrializados/Alimentação no domicílio, Selic, Câmbio, PIB Total/Agropecuária/Indústria/Serviços/…, Produção industrial, Conta corrente, Balança comercial (IndicadorDetalhe Saldo/Exportações/Importações), Resultado primário/nominal, Dívida líquida/bruta, Investimento direto no país, Taxa de desocupação.
- **IPCA annual:** 48,782 rows, `Data` 2000-01-03 → **2026-10-30** (6,731 survey dates; latest on 2026-11-07 is 2026-10-30, so ~1 week lag), `DataReferencia` 2000…2030 (year as string). Per (Data, DataReferencia) **two rows**: `baseCalculo` 0 (32,677 rows; since 2000) and 1 (16,105; since 2014-01-02) — the two calculation windows (30 vs 15 days *(from docs, not verified)*). Unique key (Data, DataReferencia, baseCalculo): 0 duplicates.

## 3. Layout
`{"Indicador":"IPCA","IndicadorDetalhe":null,"Data":"2026-10-30","DataReferencia":"2027","Media":4.8743,"Mediana":4.8478,"DesvioPadrao":0.5912,"Minimo":3.5046,"Maximo":6.0897,"numeroRespondentes":116,"baseCalculo":1}`
- Values are JSON numbers, % (IPCA % a.a.), 1–4 decimals (2 dp most common in IPCA). Earliest rows (2000-01-03) have null Minimo/Maximo/numeroRespondentes. CSV variant: comma-separated, quoted decimal commas, `null` literal.

## 4. Quirks
- Two statistic windows per survey date (baseCalculo) — must be part of the key. Entity-set names and EntityType names differ (`ExpectativasMercadoAnuais` vs `ExpectativaMercadoAnual`).
- Knowledge time = `Data` (survey date); publication is Monday for the prior week *(from docs)*, API showed 2026-10-30 as latest on Saturday 11-07.

## 5. Identity fields
`Indicador` text (no code); series_id to be built as Indicador|IndicadorDetalhe|statistic|DataReferencia.

## 6. Ephemerality
Not ephemeral; full history queryable. Past statistics could be revised *(not verified)*; archive new `Data` ranges weekly.

## 7. Open questions
- Exact definition of baseCalculo; whether old rows get restated; ExpectativasMercadoInstituicoes access.
