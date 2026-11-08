# b3_fundosnet_cda — month-end portfolios (CDA) of ETFs on Fundos.NET

Recon 2026-11-08. Parser `src/fin/ingest/fundosnet_cda.py`, fixtures `tests/fixtures/b3_fundosnet_cda/`.
Why: CVM's CDA open data (`cvm_fi_cda`) has no ETF-as-fund rows (see b3_fundosnet_daily.md).

## Access (no login; browser UA)
- Listing: `https://fnet.bmfbovespa.com.br/fnet/publico/pesquisarGerenciadorDocumentosDados?d=0&s=<offset>&l=200
  &o[0][dataEntrega]=desc&idCategoriaDocumento=6&idTipoDocumento=63&tipoFundo=3`.
- **`tipoFundo` is what restricts to ETFs** (3 = ETF: 7,838 documents; 4 = ETF RF: 290). Without it type 63 lists every
  fund type: 25,418 documents, including FIDCs. `idTipoFundo` is ignored (still 25,418).
- Document: `downloadDocumento?id=<id>`; 1–190 kB. Oldest on FNET: id 33547 (2018-09, delivered 2018-10-04).
- 164 documents sampled across the history (66 of them from the ETF-filtered listing); 162 parse, 2 are not data.

## Layouts (all values as strings; dates dd/mm/yyyy, competence MM/YYYY)
- `cda` (142 of 164): `DOC_ARQ xmlns="urn:cda"`, `CAB_INFORM` (COD_DOC, VERSAO 3.0, DT_COMPT, DT_GERAC_ARQ),
  `LISTA_INFORM/INFORM` (one per document: CNPJ_FDO, VL_PL, LISTA_ATIV). Decimal comma; thousands never separated.
  Each `LISTA_ATIV` child is an asset block holding exactly one `APLIC` (COD_TP_APLIC, EMPR_LIGADA, QTDE_DIAS_CONFID,
  `NEGOC`: TP_NEGOC, QTDE/VL_VENDAS_NEGOC, QTDE/VL_AQUIS_NEGOC, `POS_FIM`: QTDE_POS_FIM, MERC_POS_FIM). Blocks seen
  (counts over the sample): `DEMAIS_CODIF` 3,160 (COD_TP_ATIV, COD_ATIV = ticker, DT_INI_VIGEN), `DEMAIS_N_CODIF`
  1,418 (DESC, EMIS), `INV_EXT` 520 (abroad: COD_PAIS, COD_BV_MERC, COD_ATIVO_BV_MERC, NM_EMIS), `COTAS` 276
  (CNPJ_FDO of the held fund), `TIT_PUB` 239 (COD_SELIC, DT_VENC), `TIT_AGRO_CRED_PRIV` 5, `DEP_PRAZO_TIT_IF` 2
  (issuer, rating, post/pre-fixed index fields). No ISIN anywhere. Child order varies; some `NEGOC` are empty.
- `legacy` (19 of 164, ids 33547 → 501321, i.e. 2018-09 → 2023-07, so not a clean era boundary): root
  `DadosEconomicoFinanceiros`, `DadosGerais` (Competencia, Versao, DataRecebeInformacoes, CNPJFundo, NomeFundo,
  CNPJAdm, NomeAdm, ValorPatrimonioLiquido) and a flat `Carteira/Aplicacoes/Aplicacao` list (asset described by
  DescricaoTipoAtivo text, CodigoAtivo, DataInicioVigenciaAtivo, issuer, Classificacao, NegocioRealizado,
  PosicaoFinal with ValorMercado and PercentualPatrimonio; `Custo` always empty). Decimal point.
  For bonds `DataInicioVigenciaAtivo` is not an issue date (id 33547 line 1: 2021-03-01 in a 2018 report); kept as
  written in `code_valid_from`.
- Negative `MERC_POS_FIM`/`ValorMercado` occur (short or payable lines: 13 lines), as does a negative `VL_PL` (2).
- Defects handled: body declared Windows-1252 but UTF-8 (id 1240750) is read as UTF-8; CNPJ without leading
  zero (`6175696000173`) is padded to 14; a 32-byte text body (id 35023, "Ocorreu um enviar o arquivo XML.") and a
  FIDC portfolio (root `DOC_ARQ` without namespace, `APLIC_ATIVO`, id 616210) raise `NotData`.

## Parsed
`position` (one row per asset line, `line` = ordinal in the document, key doc_id+fund_cnpj+line) and `net_assets`
(one row per document), column names shared with `cvm_fi_cda.position` where the field is the same; `listing` via
`fundosnet.parse_listing`. Datasets: `carteira`, `listagem`. Unknown elements and blocks raise `LayoutError`.

## Not parsed
- Issuer id and name of a natural person (11-digit `NR_PF_PJ_EMIS`, or PF): dropped, the position is kept
  (a CPF and a person's name occurred in a `TIT_AGRO_CRED_PRIV` line of id 1368457).
- `CAB_INFORM` COD_DOC, VERSAO and the legacy NomeFundo, CNPJAdm, NomeAdm, Versao (fund and administrator names are
  in the registers).
- `COD_TP_ATIV` / `COD_TP_APLIC` stay as codes: no official table was verified, so no decoding.
- Blocks absent from the sample (swaps, derivatives, repos, private credit…) fail loudly if they appear; a full
  backfill will show which exist.
