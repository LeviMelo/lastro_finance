# bcb_ptax fixture
Full, unmodified Olinda responses, fetched 2026-11-07 ~08:37 UTC (browser UA), base `https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/`, parameter dates `'MM-DD-YYYY'`, `$format=json`.
- `CotacaoDolarPeriodo_2024-01-02_2024-01-05.json` — `CotacaoDolarPeriodo(dataInicial='01-02-2024',dataFinalCotacao='01-05-2024')` (4 rows).
- `CotacaoMoedaPeriodo_EUR_2024-01-02_2024-01-04.json` — `CotacaoMoedaPeriodo(moeda='EUR',...'01-02-2024'..'01-04-2024')` (bulletins: Abertura/Intermediário/Fechamento).
- `CotacaoDolarPeriodo_1984-11-28_1985-01-31_top3.json` — same function, `&$top=3`; shows pre-reform values (2814.0 cruzeiros).
- `CotacaoDolarDia_2026-11-06.json`, `Moedas.json` (10 currencies).
sha256: see `sha256sum *.json`; e.g. Moedas.json 248823b5dbe4d9cca03a4304a12717f34a3327202d9be70a6e8e99bb5d7ad027.
