# b3_fundosnet fixtures (copied byte-exact from raw, fetched 2026-11-07)
Documents: `https://fnet.bmfbovespa.com.br/fnet/publico/downloadDocumento?id=<id>`. Listing:
`.../pesquisarGerenciadorDocumentosDados?d=0&s=0&l=200&o[0][dataEntrega]=desc&idCategoriaDocumento=14&idTipoDocumento=41`.
Public filings; they carry the filer's contact name and phone as published (not parsed).
- `doc_1371379.xml` — TINF11 income 0.40, data-com 2026-11-06 — sha256 398f3c16…62cb
- `doc_485737.xml` — a Provento with both Rendimento and Amortizacao — sha256 c7a09212…bf4c
- `doc_496707.xml` — an Amortizacao tipo="Total" — sha256 dff6ade9…3cab
- `doc_991793_informe_mensal.xml` — a monthly report filed as a distribution notice (not data) — sha256 af6dded1…49b4dc
- `listagem_offset0.json` — listing page 0 (200 rows, newest first) — sha256 0241c51d…0fed
