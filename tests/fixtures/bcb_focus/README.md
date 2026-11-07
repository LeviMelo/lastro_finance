# bcb_focus fixture
Unmodified Olinda responses, fetched 2026-11-07 ~08:40 UTC (browser UA), base `https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/`.
- `ExpectativasMercadoAnuais_IPCA_2026-10-30.json` — `ExpectativasMercadoAnuais?$format=json&$filter=Indicador eq 'IPCA' and Data eq '2026-10-30'` (10 rows: 5 reference years x baseCalculo 0/1).
- `ExpectativasMercadoAnuais_IPCA_2000-01-03.json` — same for the earliest date (nulls in Minimo/Maximo/numeroRespondentes).
- `ExpectativasMercadoSelic_top2.json` — `$top=2&$orderby=Data desc`.
- `ExpectativasMercadoAnuais_IPCA_csv_top2.csv` — `$format=text/csv` (comma-separated, quoted pt-BR decimals).
Hashes: run `sha256sum *`.
