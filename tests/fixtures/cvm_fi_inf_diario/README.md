# Fixtures cvm_fi_inf_diario

Fetched 2026-11-07 UTC with the generic lastro-fin User-Agent. Each file = the original header line + the original lines kept; byte-exact, original encoding (cp1252, ';', CRLF). The sha256 is of the full original member.

Three header eras of the same table: CVM 175 (2023-12 on), TP_FUNDO/CNPJ_FUNDO (2021 to 2023-11) and CNPJ_FUNDO only (HIST, 2000-2020).

| file | source URL | member sha256 | lines kept |
|---|---|---|---|
| inf_diario_fi_202609.csv | https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/inf_diario_fi_202609.zip | a758fd88e6d72436fb958e6f16b67ce42708e7ca3ce5a6bc6853eb2567e31af3 | 54, filter: CNPJ_FUNDO_CLASSE in {07.593.972/0001-86 (largest NAV on 2026-09-30), 09.613.232/0001-90 (negative quota)} + first 12 rows of 00.888.897/0001-31 (subclasses) |
| inf_diario_fi_202101.csv | https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/inf_diario_fi_202101.zip | d3f06891378af6a4bf9e298b33cbda15e60fb241753a552108eae9920dc64360 | 20, filter: CNPJ_FUNDO 00.017.024/0001-53 (legacy header with TP_FUNDO) |
| inf_diario_fi_200501.csv | https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/HIST/inf_diario_fi_2005.zip (member inf_diario_fi_200501.csv) | 772a058b6250e3ad88c311f29d33e22032f5ed1a0cbde3097f3fbad362752cac | 7, first lines (HIST header without TP_FUNDO) |
| inf_diario_fi_2001.csv | https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/HIST/inf_diario_fi_2001.zip | 393b7024a4255bae696fbf498160a1c202ccbdf132cce9849206fea2d7e1eff1 | 7, first lines (empty VL_TOTAL and NR_COTST) |
