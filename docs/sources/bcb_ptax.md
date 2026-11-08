# bcb_ptax — Banco Central do Brasil: PTAX (Olinda OData)

**Tier:** P. **Recon date:** 2026-11-07. **Fixture:** `tests/fixtures/bcb_ptax/` (USD period, EUR bulletins, 1984 sample, day, Moedas; 4.6 KB).

## 1. Access
- `https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/` ; `$metadata` 200 (XML). No auth; browser UA used, no failures seen (generic UA not tested). 1 req/s.
- Call form (parameters are OData aliases, **dates `'MM-DD-YYYY'`**, strings quoted):
  `CotacaoDolarPeriodo(dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)?@dataInicial='01-02-2024'&@dataFinalCotacao='01-05-2024'&$format=json`
  `CotacaoMoedaPeriodo(moeda=@moeda,dataInicial=…,dataFinalCotacao=…)`, `CotacaoDolarDia(dataCotacao=@dataCotacao)`, `CotacaoMoedaDia(moeda,dataCotacao)`, `CotacaoMoedaAberturaOuIntermediario`, `CotacaoMoedaPeriodoFechamento(codigoMoeda,dataInicialCotacao,dataFinalCotacao)` (last two seen in $metadata only, not called). Entity set `Moedas` (no parameters). `$format=text/csv` works (`"5,5007"` quoted decimal comma).

## 2. Datasets
| dataset_id | granularity | history | notes |
|---|---|---|---|
| CotacaoDolarPeriodo | USD close PTAX (buy/sell, 5 dp) per day | **1984-12-03 → 2026-11-06**; the whole range in ONE call: 10,505 rows, 973 KB, no row cap (`$top` not needed) | one value per day (closing PTAX, ~13:06) |
| CotacaoMoedaPeriodo/Dia | per currency, all bulletins (Abertura, Intermediário ×n, Fechamento) with paridade + cotação | per currency *(only EUR 2024 and GBP 2026-11-06 sampled)* | |
| Moedas | 10 symbols: AUD CAD CHF DKK EUR GBP JPY NOK SEK USD; tipoMoeda A/B (quote convention) | n/a | |

## 3. Layout
- Dolar: `{"cotacaoCompra":4.89100,"cotacaoVenda":4.89160,"dataHoraCotacao":"2024-01-02 13:05:50.319"}`.
- Moeda: `{"paridadeCompra":1.09520,"paridadeVenda":1.09560,"cotacaoCompra":5.35270,"cotacaoVenda":5.35530,"dataHoraCotacao":"2024-01-02 10:08:28.6","tipoBoletim":"Abertura"}`. Decimals are JSON numbers with trailing zeros (Scale=5). `dataHoraCotacao` is a free-length string (1–6 fractional digits).

## 4. Quirks
- **Currency units change** (values are as-published, not rebased): 1984-12-03 = 2814.0/2828.0 (cruzeiros); jumps at 1986-03-03 (÷1000), 1989-01-16, 1993-08-02, 1994-07-01 (Real: 2750 → 1.0). Never splice without rebasing.
- Multiple rows for the same day: 8 days with 2 rows and 1 with 3 (e.g. 1984-12-03, 1990-01-03, 2001-12-21, 2025-04-23 = two identical rows 27 ms apart) — dedupe by date.
- Oldest rows have `.0` timestamps and odd hours (11:29, 16:38, 19:19).
- Cross-check: SGS 1/10813 4.8916 on 2024-01-02 vs PTAX venda 4.8916 (matches).
- Mojibake only in a Windows console; the HTTP body is UTF-8 (`Dólar`, `Intermediário`).

## 5. Identity fields
Currency symbol (ISO-like, `simbolo`); no ISIN.

## 6. Ephemerality
Not ephemeral: full history per call, intraday bulletins kept. Late-day value for D is available the same day (~13:06 close).

## 7. Open questions
- Whether published values are ever revised (the daily job re-reads the last 30 days, so a revision becomes a new series version).

## 8. Parsed (`ingest/ptax.py`, 2026-11-07)
- **Fetched:** `Moedas` first, then one `CotacaoMoedaPeriodo` per listed currency (full history 1984-01-01 → today the first time or on backfill, then the last 30 days, reaching back a week before the previous fetch if that is older). `CotacaoDolarPeriodo` is exactly the USD Fechamento rows of `CotacaoMoedaPeriodo` (10,505 identical rows) and is not fetched; the parser still reads it (`dolar_period`). Depth measured per currency: all 9 non-USD currencies and USD start 1984-11-29 except EUR (1998-12-31, the euro); one request is 11-14 MB / 7-9 s for ~67-81k bulletins; 798,021 bulletins in all.
- **Bulletins:** Abertura, Intermediário (up to ~13 a day in the 1990s), Fechamento (the PTAX; 10,505 USD days), Fechamento Interbancário (1999-10-27 → 2011-06-30, 2,856 USD rows). Parity convention from `Moedas.tipoMoeda`: A = currency units per USD (JPY 157.1), B = USD per currency unit (EUR 1.1146); `cotacao*` is always BRL per 1 unit.
- **Staging:** `quote` (all bulletins, exact decimals, `quoted_at` naive BRT), `currency`, and series `bcb_ptax:<CCY>:buy|sell` (Fechamento, one value a day: the later of the 9 days with two rows) into `observation`/`definition` -> core `series_observation`. Reparse/e2e: 797,967 quotes valid, 202,946 series observations, 0 core quarantine.
- **Quarantine (54 rows, all currencies):** `Intermediário` bulletins 1999-01-04..2002-04-30 with every rate 0 (AUD/CAD/CHF/DKK/NOK/SEK/GBP/JPY/USD 5 each, EUR 9): the source publishes zeros, not a quote; raw keeps them, rule `brl_rates_positive`.
- Cross-check: ANBIMA Quadro Indicadores 2026-11-06 USD 5.5007/5.5013 and EUR 6.1300/6.1317 equal the PTAX Fechamento rows.

