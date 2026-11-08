# Fixtures cvm_fi_cadastro

Fetched 2026-11-07 UTC with the generic lastro-fin User-Agent. Each file = the original header line + the original lines kept; byte-exact (cp1252, ';', CRLF), except `registro_fundo.csv`, whose `Diretor` column (a person's name) is blanked. The sha256 is of the full original member.

Funds kept: golden fund SPECIAL RENDA FIXA REFERENCIADO DI (CNPJ 01.597.187/0001-15, ID_Registro_Fundo 28272, class 142, adapted 2024-08-29, daily series switches 2024-10-01); fund 62437 (3 classes; class 11938, CNPJ 38.456.821/0001-00, was its own legacy fund); fund 86810 (2 new classes). The CNPJs of the legacy files: 01.597.187/0001-15, 38.456.821/0001-00, 34.831.235/0001-47, 64.144.214/0001-14, 55.068.518/0001-59.

| file | source URL | member sha256 | lines kept |
|---|---|---|---|
| cad_fi.csv | https://dados.cvm.gov.br/dados/FI/CAD/DADOS/cad_fi.csv | a432031e15cdd66f956ac491efca37f3ff9e1d91e7fe8e86b926b9b544735e21 | 1: cad_fi row of the golden fund (cancelled on adaptation) |
| cad_fi_hist_sit.csv | https://dados.cvm.gov.br/dados/FI/CAD/DADOS/cad_fi_hist.zip | 874f76aa25237bc7f1c6b63f97fde28e2eb21906d57842eba5b48c17fac97984 | 11: hist `sit` lines of the five CNPJs below |
| cad_fi_hist_denom_social.csv | https://dados.cvm.gov.br/dados/FI/CAD/DADOS/cad_fi_hist.zip | 9ea23165aad0c6d27402c1a44680b5765a8b2d313db7e5bf66a1cc56fd82d825 | 22: hist `denom_social`, same CNPJs |
| cad_fi_hist_admin.csv | https://dados.cvm.gov.br/dados/FI/CAD/DADOS/cad_fi_hist.zip | d2a2f13ebbae4218412786c0b8692b1f0a4fd8c3c3e2eb0f1463de968e9bbe75 | 6: hist `admin`, same CNPJs |
| cad_fi_hist_classe.csv | https://dados.cvm.gov.br/dados/FI/CAD/DADOS/cad_fi_hist.zip | 2539250505372edaa59510f6f1d65bf165be0eb8f633d687a20f11f476fbb313 | 6: hist `classe`, same CNPJs |
| registro_fundo.csv | https://dados.cvm.gov.br/dados/FI/CAD/DADOS/registro_fundo_classe.zip | 83d4a8a8b9850a90ea19e092dd7c0f9bc028d6fd2e8e864a6dfc37f348b931b8 | 3: ID_Registro_Fundo 28272, 62437, 86810; `Diretor` blanked |
| registro_classe.csv | https://dados.cvm.gov.br/dados/FI/CAD/DADOS/registro_fundo_classe.zip | 666a25dc6cdc09f036daeece20c9061ca1b1f49abc13835450b279947b632c26 | 6: classes of those three funds |
| registro_subclasse.csv | https://dados.cvm.gov.br/dados/FI/CAD/DADOS/registro_fundo_classe.zip | 7d4a73657882fb78f6c2b0ddc1ad45300cbbca886e74431ea59cf0015668c94a | 5: subclasses of those classes + ID_Registro_Classe 81 |
