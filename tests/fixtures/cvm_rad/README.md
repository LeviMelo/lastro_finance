# cvm_rad fixtures

`020800ITR30-09-2024v1.trimmed.xml`: the statements XML of Tegma Gestão Logística S.A.'s ITR for 2024-09-30, version 1
(RAD document 142508), trimmed to a few accounts. Fetched 2026-11-08 UTC from
https://www.rad.cvm.gov.br/ENETCONSULTA/frmDownloadDocumento.aspx?CodigoInstituicao=1&NumeroSequencialDocumento=142508
(zip 8,188,722 bytes, sha256 `f80d6235def5a409e5882767f485a8a440cce314c27a909f57bc69b3ecf6f47b`). The original member
`020800ITR30-09-2024v1.xml` is 6,050,491 bytes, sha256 `82e1e22e7666177f5cd31b72c9f287d0c926775220016aa8e369b44ef046595d`.

How it was cut (the element texts are the original's, byte for byte; the file as a whole is re-serialised, so its own
sha256 is `4216e68a5b6e2efaa894ef8f2377c3c6cb5a6d628126ff1bfdae1d424343ee7e`, 15,450 bytes):
- every `ImagemObjetoArquivoPdf` text stripped (what `extract_statements` does), then `Documento/ResponsavelDocumento`,
  `Justificativas`, `PareceresDeclaracoes` and `AnexosDocumento` removed;
- `DfConsolidadas`: first 3 accounts of BPA, BPP, DFC, DVA, first 2 of DRA, first 4 of DRE; DMPL keeps its 2 periods with
  3 accounts each; `DfIndividuais`: first 3 accounts of BPA only.

It shows what the open-data CSV hides: values written with pt-BR thousand dots (`1.244.763`), quarter and year-to-date
columns of the DRE, `ExercicioAnterior` on the balance sheet, `EscalaMoeda` 2 (MIL) with `EscalaQtdAcoes` 1.

## Legacy layout (`legacy_5110/`, `legacy_103318/`)
The four members `extract_legacy` keeps from the nested `.dfp`/`.itr` zip of a legacy RAD download, fetched 2026-11-08 UTC from
the same URL pattern (`NumeroSequencialDocumento=<doc>`):
- `legacy_5110/`: Companhia de Bebidas das Américas (Ambev) DFP 2010-12-31, version 1, RAD document 5110 (zip 6,758,690 bytes,
  sha256 `ca01a66424bfd5d531a1435db18f9a1462edb7629a633b7392e505dbb4757ddf`; nested `018112201012310401.dfp`).
- `legacy_103318/`: Itaú Unibanco Holding ITR 2021-03-31, version 1, document 103318 (zip 10,371,955 bytes, sha256
  `e3281e361e2e2f7e93ef2a93b6727251ab366154669cf7656c0195f629420dd2`; nested `019348202103310301.itr`).

`Documento.xml`, `PeriodoDemonstracaoFinanceira.xml` and `ComposicaoCapitalSocialDemonstracaoFinanceiraNegocios.xml` are the
original members, byte for byte (they hash to
5110 `d8250c55…`, `c9ab5b31…`, `2bce4ee6…`; 103318 `85b5035e…`, `ce60f476…`, `9782a71f…`). `InfoFinaDFin.xml` is cut to whole
`<InfoFinaDFin>` records sliced from the original bytes: 5110 keeps the first 3 accounts of each statement and consolidation
(DMPL: 3 per period block), 48 of 810 records (302,514 of 5,103,105 bytes, original sha256 `7625475b…`); 103318 keeps 2
accounts of the balance sheet, DRE and DMPL, 16 records (151,689 of 5,634,975 bytes, original sha256 `6adb983c…`).
They show the layout: `ValorConta1..12`, the period id of a DMPL record, a 7-column individual DMPL (103318), zero lines, a
Q1 ITR whose quarter and year to date share their dates.
