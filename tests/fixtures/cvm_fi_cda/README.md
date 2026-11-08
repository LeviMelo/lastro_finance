# Fixtures cvm_fi_cda

Fetched 2026-11-07 UTC with the generic lastro-fin User-Agent. Each file = the original header line + the original lines kept; byte-exact, original encoding (cp1252, ';', CRLF). The sha256 is of the full original member.

The first six data lines of each parsed member (positions blocks 1-8 and PL of 2026-10, plus three members of 2023-01 with the legacy header). The CPF of a natural-person issuer found in the real files is not committed; the test builds a synthetic line.

| file | source URL | member sha256 | lines kept |
|---|---|---|---|
| cda_fi_BLC_1_202610.csv | https://dados.cvm.gov.br/dados/FI/DOC/CDA/DADOS/cda_fi_202610.zip | c55a8417d20fe314e348a86df2472b6678a3df3e8f8a51581f5af7e5cd52f36c | 6, first lines |
| cda_fi_BLC_2_202610.csv | https://dados.cvm.gov.br/dados/FI/DOC/CDA/DADOS/cda_fi_202610.zip | 24ef46d2394436fce2bb770fc8a8235e17dfa95b356830927994b5a75e3a8b0f | 6, first lines |
| cda_fi_BLC_3_202610.csv | https://dados.cvm.gov.br/dados/FI/DOC/CDA/DADOS/cda_fi_202610.zip | 561815123cf6f522ff06a0f2d7b800296b298c875364808a7c10bd21d640276e | 6, first lines |
| cda_fi_BLC_4_202610.csv | https://dados.cvm.gov.br/dados/FI/DOC/CDA/DADOS/cda_fi_202610.zip | a9c027ef8c976faa2cfbafc0a6377365750a087585dbbf0a93db9fcd2dacb261 | 6, first lines |
| cda_fi_BLC_5_202610.csv | https://dados.cvm.gov.br/dados/FI/DOC/CDA/DADOS/cda_fi_202610.zip | 483b877622efd9a0257fbaab896aae72a74102875afbb72426974a4cd07ee52c | 6, first lines |
| cda_fi_BLC_6_202610.csv | https://dados.cvm.gov.br/dados/FI/DOC/CDA/DADOS/cda_fi_202610.zip | f890dd56e6714eb595c0c376e871088f04efd5545c6fb3892975c5ba3e234c8b | 6, first lines |
| cda_fi_BLC_7_202610.csv | https://dados.cvm.gov.br/dados/FI/DOC/CDA/DADOS/cda_fi_202610.zip | 17609393fb291e72eb8d71344afed64db33b2f5d6fd0ca2fb94a364600109746 | 6, first lines |
| cda_fi_BLC_8_202610.csv | https://dados.cvm.gov.br/dados/FI/DOC/CDA/DADOS/cda_fi_202610.zip | 8e713e83e2d5fa8bbd2f27ce6c554ab06cd063b1588971b1d19dabf804bf10b5 | 6, first lines |
| cda_fi_PL_202610.csv | https://dados.cvm.gov.br/dados/FI/DOC/CDA/DADOS/cda_fi_202610.zip | 901d63016ddc76f28acf3629f74b0d9431d9742790f343ac936a9230e63991cb | 6, first lines |
| cda_fi_BLC_2_202301.csv | https://dados.cvm.gov.br/dados/FI/DOC/CDA/DADOS/cda_fi_202301.zip | 1a306a09c85dd57072c836763cd0f2f5318f8bcb29f1fd3cd405c77a103765bd | 6, first lines (legacy header TP_FUNDO/CNPJ_FUNDO, CNPJ_FUNDO_COTA) |
| cda_fi_BLC_6_202301.csv | https://dados.cvm.gov.br/dados/FI/DOC/CDA/DADOS/cda_fi_202301.zip | 969e212bb5d84a318472de7fd34648505e6a2b40728af1bf98088ea8213cac40 | 6, first lines (legacy header TP_FUNDO/CNPJ_FUNDO, CNPJ_FUNDO_COTA) |
| cda_fi_PL_202301.csv | https://dados.cvm.gov.br/dados/FI/DOC/CDA/DADOS/cda_fi_202301.zip | 982df62deb28e579cb7d7c8aacc7fc1c42803fdbd7504ab9988101bd15ece8df | 6, first lines (legacy header TP_FUNDO/CNPJ_FUNDO, CNPJ_FUNDO_COTA) |
