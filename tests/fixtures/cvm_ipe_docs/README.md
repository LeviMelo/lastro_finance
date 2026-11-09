# cvm_ipe_docs fixtures

Two IPE filings as RAD served them on 2026-11-09, byte for byte. Each was fetched with a browser User-Agent and no login from
`https://www.rad.cvm.gov.br/ENET/frmDownloadDocumento.aspx?Tela=ext&descTipo=IPE&CodigoInstituicao=1&numProtocolo=<P>&numSequencia=<S>&numVersao=<V>`.
Both were served as `text/html`.

| file | protocol / sequence / version | format | sha256 | states |
|---|---|---|---|---|
| `telebras_266245.doc` | 266245 / 0 / 0 | Word 97 | `c61ba54c88904dde815c38b827113b00c46e82650e42b32a21f121a7b303fcba` | Telebras AGE call, 2010-11: regrouping "10.000 (dez mil) ações para 1 (uma)" |
| `bttl_492206.pdf` | 492206 / 34954 / 1 | PDF | `04e0f827b00b348396ad5d9c22a5da3c9e034f0eb222bbd19ecf0a25d5ff9aa6` | notice to shareholders, 2015-11-19: regrouping "25 (vinte e cinco) … para 1 (uma)" |
