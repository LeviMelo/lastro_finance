# Fixtures cvm_fii

Fetched 2026-11-07 UTC with the generic lastro-fin User-Agent. Each file = the original header line + the original lines kept; byte-exact, original encoding (cp1252, ';', CRLF). The sha256 is of the full original member.

2026 files: lines of HGLG11 (11.728.688/0001-47), KNRI11 (12.005.956/0001-65) and a fund with negative net assets (00.613.094/0001-74). 2016 files: the first lines of the member, to pin the legacy header (CNPJ_Fundo, Nome_Fundo; no CRI_CRA/LCI_LCA in the balance sheet).

| file | source URL | member sha256 | lines kept |
|---|---|---|---|
| inf_mensal_fii_geral_2026.csv | https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS/inf_mensal_fii_2026.zip | 9bb9dec161767e8ef20340d09f88c41e99c0835fbb82e73207d900cddd6dd751 | 27, filter: CNPJ in {HGLG11, KNRI11, negative-NAV fund} |
| inf_mensal_fii_complemento_2026.csv | https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS/inf_mensal_fii_2026.zip | c814db81eb4aaa853f8724727b01805e8782813e2969864a02c01da8ab8652dd | 27, filter: CNPJ in {HGLG11, KNRI11, negative-NAV fund} |
| inf_mensal_fii_ativo_passivo_2026.csv | https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS/inf_mensal_fii_2026.zip | f10cf89456c262db5aeb63b20af40fc02339e9460e3c03fc594ed42c9ca7286d | 27, filter: CNPJ in {HGLG11, KNRI11, negative-NAV fund} |
| inf_trimestral_fii_geral_2026.csv | https://dados.cvm.gov.br/dados/FII/DOC/INF_TRIMESTRAL/DADOS/inf_trimestral_fii_2026.zip | bc9618be9f7ca760c41793eaa6d292497fd14b2af1fb76e21dc31f742ea7ffa9 | 6, filter: CNPJ in {HGLG11, KNRI11, negative-NAV fund} |
| inf_trimestral_fii_imovel_2026.csv | https://dados.cvm.gov.br/dados/FII/DOC/INF_TRIMESTRAL/DADOS/inf_trimestral_fii_2026.zip | 2488fbd47e8a67748295551693895810ce18457e350db48264e75f0bd6cc0d28 | 110, filter: CNPJ in {HGLG11, KNRI11, negative-NAV fund} |
| inf_trimestral_fii_ativo_2026.csv | https://dados.cvm.gov.br/dados/FII/DOC/INF_TRIMESTRAL/DADOS/inf_trimestral_fii_2026.zip | db4cdc6021bbf253585cd28a50ca41541aca713c038497e6697c89446c68d539 | 191, filter: CNPJ in {HGLG11, KNRI11, negative-NAV fund} |
| inf_anual_fii_geral_2026.csv | https://dados.cvm.gov.br/dados/FII/DOC/INF_ANUAL/DADOS/inf_anual_fii_2026.zip | 1d59d7c5aa4e52abd378d91c0eea1c5e91405d6fc3f73aa8f185b446aedec537 | 1, filter: CNPJ in {HGLG11, KNRI11, negative-NAV fund} |
| inf_mensal_fii_geral_2016.csv | https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS/inf_mensal_fii_2016.zip | 6298f21ff72ab9ab88f1b0807bcb4684e6ab89b33f79c4bad9d081577fe6943f | 3, first lines (legacy header CNPJ_Fundo) |
| inf_mensal_fii_complemento_2016.csv | https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS/inf_mensal_fii_2016.zip | 3ac91aa1f6ea68b7d18e39fd2b3a71a8dd448c37592c7886cdcaac8aed70558e | 3, first lines (legacy header CNPJ_Fundo) |
| inf_mensal_fii_ativo_passivo_2016.csv | https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS/inf_mensal_fii_2016.zip | 32006a2337e0d65688f376df1856385c7b10dbaeda40b752598bd0d237c75fe1 | 3, first lines (legacy header CNPJ_Fundo) |
| inf_trimestral_fii_geral_2016.csv | https://dados.cvm.gov.br/dados/FII/DOC/INF_TRIMESTRAL/DADOS/inf_trimestral_fii_2016.zip | 529c67acac76f1b2799af74604b03cbbfcddbc87e15b12ff5e4d2bd360ff7235 | 2, first lines (legacy header CNPJ_Fundo) |
