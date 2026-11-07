# cvm_dfp_itr fixtures

Fetched 2026-11-07 UTC from https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/dfp_cia_aberta_2024.zip
(13,397,602 bytes; Last-Modified Sun, 01 Nov 2026 10:23:49 GMT; sha256 of the zip `2071e7908c2d1fa945b21b3d6a982eb41b1550360f19e5185cb5eb6fbf9a8fb9`).
Each file = the zip member's header line + every line whose CNPJ_CIA is Itau Unibanco Holding (60.872.504/0001-23) or
Petrobras (33.000.167/0001-01). Byte-exact lines, cp1252, ';', CRLF.

| file | member | lines kept (excl. header) |
|---|---|---|
| dfp_cia_aberta_2024.csv | dfp_cia_aberta_2024.csv (index, 873 rows in full) | 2 |
| dfp_cia_aberta_BPA_con_2024.csv | consolidated asset side (62,680 rows in full) | 212 (Itau 82, Petrobras 130) |
| dfp_cia_aberta_DRE_con_2024.csv | consolidated income statement (32,776 rows in full) | 168 (Itau 82, Petrobras 86) |
  9942fd96508afa28e7302425d70ed704d4b11ced29d61adfc70f89901ba0a2ea *dfp_cia_aberta_2024.csv
  d8d51c073daed3d2b19a77428bebb583daf71f3a3411991dc6f6f5f2145d898a *dfp_cia_aberta_BPA_con_2024.csv
  168a437ea2c2f418ce9a274ef49eef0c6946a5e422b195b4b10b051b72ca41b8 *dfp_cia_aberta_DRE_con_2024.csv
