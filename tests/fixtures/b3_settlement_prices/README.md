# Fixtures: b3_settlement_prices (fetched 2026-11-07 ~08:30 UTC, byte-exact)
| file | request | sha256 |
|---|---|---|
| bdi_ConsolidatedTradesDerivatives_20261106_p1_take5.json | POST https://arquivos.b3.com.br/bdi/table/ConsolidatedTradesDerivatives/2026-11-06/2026-11-06/1/5 body `{}` (Content-Type: application/json) | 9cd8e082de75aa8889162aa52612714947e6783390a3a2f29a67a530dd928545 |
| bdi_ConsolidatedTradesDerivatives_20261106_DI1F27.json | same, take=100, `?filter=` base64("DI1F27") = RElGMjc= | 1b19b4e684a03f380db897a88fe38700b39eb8be4af882020e7df30ce680c435 |
| bdi_workdays_20261106.json | GET https://arquivos.b3.com.br/bdi/table/workdays?date=2026-11-06&limitDate=D-21 | a0cba4515f1e6e5cd38956d8b96fc476785453763a5562d68cd1bc29a7ec604d |
