# cvm_fca - CVM: Formulario Cadastral (FCA)

**Tier:** P. **Recon date:** 2026-11-07. **Fixture:** `tests/fixtures/cvm_fca/` (2026 index, geral and valor_mobiliario; 2010 index and valor_mobiliario). Fixture lines are byte-exact (cp1252): the header plus the rows of Itau 60.872.504/0001-23, Petrobras 33.000.167/0001-01, Natura &Co 32.785.497/0001-97 (registration cancelled 2025-07-01, by incorporation) and BRF 01.838.723/0001-27 (BRFS3 trading ended 2025-09-22).

Every statement was measured on 2026-11-07 against a real response unless marked *(not verified)*. Recon was cut short by a usage-limit stop; gaps are listed under Open questions.

## 1. Access
- HTTPS file tree https://dados.cvm.gov.br/dados/CIA_ABERTA/ (nginx autoindex behind Cloudflare). No auth. A generic UA worked; no blocking was seen.
- Headers: `Last-Modified`, `ETag` (nginx style, mtime-hex/size-hex) and `Content-Length`. `If-None-Match` and `If-Modified-Since` both return **304**. `Accept-Ranges: bytes` gives 206, so single zip members can be read without the whole zip (central directory first, then member ranges). Cloudflare `Cache-Control: max-age=14400`.
- The autoindex shows times in BRT (UTC-3), and Last-Modified is in GMT.
- CKAN API (`/api/3/action/package_list`, `package_show`): *(not verified)*.
- Regeneration seen: the current year and the four years before it were all rewritten on 2026-11-01 (a Sunday, about 07:00-08:50 BRT), so the cycle looks weekly *(cadence inferred from one listing)*. Older years are frozen, e.g. 2021 last written 2025-12-28 and 2020 on 2024-12-29. So a year is rewritten for about 5 years after it ends.

## 2. Datasets
| dataset_id | granularity | history | URL |
|---|---|---|---|
| fca_cia_aberta | one zip per year of DT_REFER (always YYYY-01-01) | 2010-2026 (330-455 KB) | DOC/FCA/DADOS/fca_cia_aberta_YYYY.zip; DOC/FCA/META/fca_cia_aberta.zip |

## 3. Layout
- Zip members (verified for 2010 and 2026): fca_cia_aberta_YYYY.csv (the index), auditor, canal_divulgacao, departamento_acionistas, dri, endereco, escriturador, geral, pais_estrangeiro_negociacao, valor_mobiliario.
- **Index** columns: CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;CD_CVM;CATEG_DOC;ID_DOC;DT_RECEB;LINK_DOC.
  - It holds **every version**. In 2026, 432 companies had 1 version, 168 had 2, and the maximum was 9.
  - DT_RECEB is a date only; it is the knowledge time.
  - CD_CVM is zero-padded to 6 characters (009512), unlike the cadastro, which has 9512.
- **valor_mobiliario** columns: CNPJ_Companhia;Data_Referencia;Versao;ID_Documento;Nome_Empresarial;Valor_Mobiliario;Sigla_Classe_Acao_Preferencial;Classe_Acao_Preferencial;Codigo_Negociacao;Composicao_BDR_Unit;Mercado;Sigla_Entidade_Administradora;Entidade_Administradora;Data_Inicio_Negociacao;Data_Fim_Negociacao;Segmento;Data_Inicio_Listagem;Data_Fim_Listagem.
- **geral** columns include Nome_Empresarial, Nome_Empresarial_Anterior, Data_Nome_Empresarial, Codigo_CVM, Situacao_Registro_CVM (with its date), Categoria_Registro_CVM, Setor_Atividade, Situacao_Emissor, Especie_Controle_Acionario and fiscal-year end.

## 4. Quirks
- **The sub-tables hold only the latest version per company**, while the index lists all versions. Example: Itau 2026 has index versions 1 and 2, but valor_mobiliario has version 2 only. Earlier versions survive only through LINK_DOC (RAD ENET).
- **Codigo_Negociacao is empty in all 635 rows of 2010.** In 2018, 477 of 751 rows are filled (ITUB3/4, PETR3/4). The first year with tickers is between 2011 and 2018 *(not verified)*.
- Dates are unstable across years. PETR3 Data_Inicio_Negociacao is 1980-08-08 in FCA 2010, 1968-08-27 in 2018, and 2018-05-14 in 2026. Treat them as weak evidence.
- Ticker cells can hold a wildcard ("PETR*" for debentures in 2018) or free text ("NAO HA").
- Delisting shows up as Data_Fim_Negociacao: BRF BRFS3 has 2025-09-22, while BRF's registration stays ATIVO (Categoria B since 2025-10-30).
- Encoding is cp1252, ';' separator, CRLF.

## 5. Identity fields
- CNPJ, CVM_CODE.
- Codigo_Negociacao maps to TICKER, per security kind and class, as of DT_RECEB.
- Segmento maps to the governance-segment attribute.
- Nome_Empresarial_Anterior maps to issuer_name history.

## 6. Ephemerality
Yearly files persist. Versions superseded within a year are lost from the sub-tables, so polling weekly and keeping each zip version preserves them.

## 7. Open questions
- The first year with tickers.
- Whether old zips change content when rewritten (2010-2019 were rewritten on 2024-03-04).
- PLAN 4.4 says FCA maps CNPJ to tickers over time. That holds only from about 2018, with one snapshot per year.
