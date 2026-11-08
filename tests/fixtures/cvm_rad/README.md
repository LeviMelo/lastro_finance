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
