# bcb_sgs fixtures (fetched 2026-11-07 ~08:20 UTC, whole responses, byte-exact, not cut)
- `cdi_2024q1.json`: https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados?formato=json&dataInicial=01/01/2024&dataFinal=31/03/2024 — sha256 07da19ef44969f039e73a2d10ac48f156037584f919a7dc00f6573a9a359a576
- `cdi2024_25.json`: same series, dataInicial=01/01/2024&dataFinal=10/01/2025 — sha256 ca884c544bbd548303d573d1337dcf694943061672cdfea09fe2be470698416c
- Accumulated-factor test values (BCB Calculadora do Cidadão, "Correção pelo CDI", 100% CDI,
  https://www3.bcb.gov.br/CALCIDADAO/publico/corrigirPeloCDI.do?method=corrigirPeloCDI&aba=5&dataInicial=…&dataFinal=…&valorCorrecao=1000,00&percentualCorrecao=100,00):
  02/01/2024→01/04/2024 = **1,02621059**; 02/01/2024→02/01/2025 = **1,10875983**.
  Reproduced from `cdi2024_25.json`: product of (1+valor/100) over days d with start ≤ d < end (end excluded), rounded half-up to 8 dp
  (16-dp truncation of the running product gives the same 8 dp).

## Series parser fixtures (copied byte-exact from raw, fetched 2026-11-07 18:19–20:21 UTC)
- `meta_433.xml`, `meta_226.xml`: SOAP `getUltimoValorXML` (POST https://www3.bcb.gov.br/wssgs/services/FachadaWSSGS,
  body `ingest/series.sgs_meta_envelope(code)`) — sha256 d4b2d95a…c221, 95d89ed5…d921
- `tr_226_2026-10-08_2026-11-07.json`: sgs.226 `dataInicial=08/10/2026&dataFinal=07/11/2026` (rows with `dataFim`) —
  sha256 390ea7f7…3e12
- `m2_27810_all.json`: sgs.27810 whole history, `formato=json`; its first rows (2001-08..11) have `"valor": null` —
  sha256 9fc5414c…a30a
- `blocked_page_200.html`: sgs.25 `dataInicial=01/02/2021&dataFinal=07/11/2026` answered HTTP 200 with an HTML
  "Requisição inválida!" page — sha256 b77c7683…4306
