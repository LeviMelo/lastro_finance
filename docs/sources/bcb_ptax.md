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
- Whether published values are ever revised; PTAX series start/depth for non-USD currencies; bulletins' earliest date.
