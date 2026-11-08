# bcb_ptax fixture
Full, unmodified Olinda responses, fetched 2026-11-07 ~08:37 UTC (browser UA), base `https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/`, parameter dates `'MM-DD-YYYY'`, `$format=json`.
- `CotacaoDolarPeriodo_2024-01-02_2024-01-05.json` — `CotacaoDolarPeriodo(dataInicial='01-02-2024',dataFinalCotacao='01-05-2024')` (4 rows).
- `CotacaoMoedaPeriodo_EUR_2024-01-02_2024-01-04.json` — `CotacaoMoedaPeriodo(moeda='EUR',...'01-02-2024'..'01-04-2024')` (bulletins: Abertura/Intermediário/Fechamento).
- `CotacaoDolarPeriodo_1984-11-28_1985-01-31_top3.json` — same function, `&$top=3`; shows pre-reform values (2814.0 cruzeiros).
- `CotacaoDolarDia_2026-11-06.json`, `Moedas.json` (10 currencies).
sha256: see `sha256sum *.json`; e.g. Moedas.json 248823b5dbe4d9cca03a4304a12717f34a3327202d9be70a6e8e99bb5d7ad027.
Added 2026-11-07 (same base URL and UA, `CotacaoMoedaPeriodo`, `$format=json`, byte-exact):
- `CotacaoMoedaPeriodo_USD_1999-10-27_1999-10-27.json` (moeda 'USD', 10-27-1999..10-27-1999; includes Fechamento Interbancario) sha256 52df22abd9355b59858d05095b5fd1363ce7f4ad934b624c4555d4db36dee524
- `CotacaoMoedaPeriodo_USD_2025-04-23_2025-04-23.json` (two Fechamento rows 13 ms apart) sha256 7ccc5267528e7e600b2241a0c5af4344a6af86756bb74e7de5c161615ec916a2
- `CotacaoMoedaPeriodo_JPY_2024-12-30_2024-12-31.json` (type A currency, year-end half day) sha256 9b6753844905b778cc7b2c82d76d719c6b9a216896fd735ba0d58866a4ac5a3d
