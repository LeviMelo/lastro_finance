# b3_fundosnet — B3 Fundos.NET: structured distribution notices of FIIs and Fiagros

**Tier:** P (B3's public filing system; the JSON endpoint is undocumented). **Recon date:** 2026-11-07.

## 1. Access
- Listing: `GET https://fnet.bmfbovespa.com.br/fnet/publico/pesquisarGerenciadorDocumentosDados?d=0&s=<offset>&l=200
  &o[0][dataEntrega]=desc&idCategoriaDocumento=14&idTipoDocumento=41` → JSON `{data, recordsFiltered, recordsTotal}`.
  Browser UA, no login or cookie. `l` = 500 → 302 (cap between 200 and 500); no category filter → 0 rows. robots.txt
  404.
- Document: `GET .../downloadDocumento?id=<id>` → XML (~1 KB).

## 2. Content
- 36,584 notices "Aviso aos Cotistas – Estruturado / Rendimentos e Amortizações", **2016-11-30 → today** (ids from
  6959). Nothing before 2016, the system's start. Other categories exist (Fato Relevante 15,819 from 2016-04; Informe
  Mensal 702,422 from 2016-06) and are not archived.
- Listing row: id, `dataEntrega` (dd/mm/yyyy hh:mm, **knowledge time to the minute**), dataReferencia, fund,
  `nomePregao`, versao, status.
- XML: `DadosGerais` (NomeFundo, CNPJFundo, CodISINCota, CodNegociacaoCota…) and `InformeRendimentos/Provento`
  (CodISIN, CodNegociacao, `Rendimento` {DataBase = data-com, ValorProvento per unit, DataPagamento,
  PeriodoReferencia, RendimentoIsentoIR}, `Amortizacao`).
- Example: TINF11, 0.40 per unit, data-com 2026-11-06, paid 2026-11-13, delivered 2026-11-06 18:08.

## 3. Ephemerality and cost
- Not ephemeral. The full history is 183 listing pages + 36,584 documents, ≈ 10 h at 1 request/s; a day adds a few
  dozen.
