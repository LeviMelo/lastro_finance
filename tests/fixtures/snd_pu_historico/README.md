# snd_pu_historico fixtures

Byte-exact answers of `GET https://www.debentures.com.br/exploreosnd/consultaadados/emissoesdedebentures/puhistorico_e.asp?op_exc=False&ativo=<ticker>&dt_ini=01/01/1980&dt_fim=08/11/2026`,
fetched 2026-11-08 ~01:40 BRT (Latin-1, CRLF; see `docs/sources/snd_pu_historico.md`).

| file | ticker | bytes | rows | sha256 |
|---|---|---|---|---|
| `ZZDT21.txt` | ZZDT21 | 47242 | 643 | `d3f5701740443f0f4213ff240f33ee88fc62f130eb1f91e19bfecd1d2a7b7140` |
| `SABP12.txt` | SABP12 | 56522 | 737 | `f7f2ae3e5c70c227866ce09ce23bd9e89af4bdd7ac53fac8a96bb842f45d9b96` |
| `VALE23_empty.txt` | VALE23 | 138 | 0 | `cfe797277847c32a7dd18fac0f643173312a808fbe13c427f99a0b708b44ac40` |
