# b3_fundosnet_daily — Fundos.NET daily reports of ETFs

Recon 2026-11-08. Connector `FundosNetInformeDiario` (src/fin/ingest/alternates.py), parser
`src/fin/ingest/fundosnet_daily.py`, fixtures `tests/fixtures/b3_fundosnet_daily/`.

## Why this source
- ETFs are CVM type FIIM (279 classes in `FI/CAD/DADOS/registro_classe.csv`; BOVA11 is class CNPJ
  10406511000161). CVM's INF_DIARIO holds BOVA11 2008-11-28 → 2018-09-06 only, and 202610 has 0 FIIM rows. CVM's
  delivery log (`FI/DOC/ENTREGA`) shows FIIM daily reports arriving through FNET (`Sistema_Origem=FNET`). So the
  values exist only in Fundos.NET; CDA and PERFIL_MENSAL have no ETF-as-fund rows either.
- BOVA11 on FNET starts 2018-09-10, so it joins CVM's series with no gap (2018-09-07 was a holiday).

## Access (no login; browser UA)
- Listing: `https://fnet.bmfbovespa.com.br/fnet/publico/pesquisarGerenciadorDocumentosDados?d=0&s=<offset>&l=200
  &o[0][dataEntrega]=desc&idCategoriaDocumento=6&idTipoDocumento=64`. Category 6 is "Informes Periódicos" and type 64
  is "Informe Diário", from `listarTodosTiposPorCategoriaETipoFundo?idTipoFundo=3&idCategoria=6`. The FNET fund
  types are 3 ETF and 4 ETF RF.
- Counts: 225,340 documents (215,523 ETF + 9,817 ETF RF, so the type covers only ETFs), the first delivered
  2018-07-02 for 2018-06-29. The rows carry no CNPJ (`cnpjFundo` null); the XML does.
- Document: `downloadDocumento?id=<id>` returns an XML of 0.5–1 kB. HEAD answers 520, so use GET.
- Also under category 6 for ETFs: type 63 CDA (7,838 documents), 65 Balancete, 30 Demonstrações Financeiras.

## Layout (documents of 2018, 2022, 2024 and 2026)
- Root `DOC_ARQ`. 2018: no namespace, `CAB_INFORM` with CNPJADM, CNPJ_FDO and NOME_FDO, plus `INFORM/DIA_COMPT`
  (the day). 2022 onward: namespace `urn:infdiario`, `CNPJ_FDO` inside `INFORM`, VERSAO 3.0 (2024) or 4.0 (2026),
  sometimes declared Windows-1252, sometimes with an XML comment naming the administrator's internal code.
- Fields, all with a decimal comma:
  - `DT_COMPT` (dd/mm/yyyy, the NAV date) and `DATA_PROX_PL`;
  - `VL_QUOTA` (up to 12 decimals);
  - `PATRIM_LIQ`, `VL_TOTAL`, `CAPTC_DIA`, `RESG_DIA`, `VL_TOTAL_SAI`, `VL_TOTAL_ATV`;
  - `NR_COTST`.
- `LISTA_COTST_SIGNIF/COTST_SIGNIF` (TP_PESSOA, CPF_CNPJ_COTST, PR_COTST) may name a person, so it is not parsed.
- Knowledge time: `dataEntrega` in the listing, usually D+1 around midday. Re-deliveries get a new id and
  `versao` > 1, so every version is kept.

## B3 listed-funds pages
`sistemaswebb3-listados.b3.com.br/fundsPage/main/etf` answered 500 to curl and the root 403. These were not
diagnosed further, because FNET carries the values; iNAV and issuer pages are not used.
