# Fixtures cvm_ipe

Fetched 2026-11-07 UTC. Each file = header line + every line matching CNPJ of Itau Unibanco Holding (60.872.504/0001-23), Petrobras (33.000.167/0001-01), Natura &Co Holding (32.785.497/0001-97, registration cancelled 2025-07-01 by incorporation) or BRF (01.838.723/0001-27, BRFS3 trading ended 2025-09-22). Byte-exact lines, original encoding (latin-1/cp1252, ';', CRLF).

| file | source URL | member | sha256 of full original | lines kept |
|---|---|---|---|---|
| ipe_cia_aberta_2025.csv | https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/DADOS/ipe_cia_aberta_2025.zip | ipe_cia_aberta_2025.csv | 8e0be043281fc12d118554cb270ece498881cb5b6ca97fb777c18fb95494e782 | 748 |

## PDFs (Link_Download test, 2026-11-07 UTC)
Byte-exact responses of `Link_Download` (URL as in the CSV, browser UA, no cookies), saved with a .pdf name; the server sends `Content-Type: text/html` and `Content-disposition: attachment; filename=019348000101011.pdf` for all of them, the body is a PDF 1.6.

| file | protocolo (Versao 1) | Data_Entrega | bytes | sha256 |
|---|---|---|---|---|
| itub_fato_relevante_2025-02-05_bonificacao10pct.pdf | 019348IPE050220250104569311-22 (numProtocolo=1330897) | 2025-02-05 | 255378 | a5a8e41baf026da1b1f0bcd4346dcdb2869d3792f2f8778794d78bc654b51269 |
| itub_fato_relevante_2025-12-18_bonificacao3pct.pdf | 019348IPE181220250198198217-32 (numProtocolo=1459139) | 2025-12-18 | 152889 | 3427b8b809ceb2e119a8d6d29ac6841ebac35d74a3c9373888910b5af03f27ef |
| itub_aviso_acionistas_2025-04-07_fracoes.pdf | 019348IPE070420250104575405-18 (numProtocolo=1358219) | 2025-04-07 | 176740 | ae1ece9adb6982b015412aea259b1801d4637c6ed734e069fe623fec66c64fbe |
