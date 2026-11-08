# Fixtures cvm_vlmo

Fetched 2026-11-08 UTC from https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/VLMO/DADOS/vlmo_cia_aberta_2025.zip.
Each file holds the header line plus byte-exact lines (cp1252, `;`, CRLF) of the companies below whose free-text
field is empty. Lines with free text are left out because it can name people: `Motivo_Reapresentacao` in the
index and `Descricao_Movimentacao` in the movements. The parser does not read those fields.

Companies: Itaú Unibanco Holding (60.872.504/0001-23), Natura &Co Holding (32.785.497/0001-97, registration
cancelled 2025-07-01 by incorporation), BRF (01.838.723/0001-27, BRFS3 trading ended 2025-09-22), and, in the index
only, Petrobras (33.000.167/0001-01).

| file | member | sha256 of the full member | lines kept |
|---|---|---|---|
| vlmo_cia_aberta_2025.csv | vlmo_cia_aberta_2025.csv | 92c07fec86ac742b925d095e917cb3f627ba2a23f0226bc9a61ae3117e7cbdf5 | 41 |
| vlmo_cia_aberta_con_2025.csv | vlmo_cia_aberta_con_2025.csv | ae3c8715549c8be38a3feb52da8640d7264793159b67ec433b3880cee851d42f | 1,200 |
