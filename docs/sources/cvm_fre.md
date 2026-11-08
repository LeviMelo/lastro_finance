# cvm_fre - CVM: Formulario de Referencia (FRE)

**Tier:** P. **Recon date:** 2026-11-07. **Fixture:** `tests/fixtures/cvm_fre/` (2022 index, capital_social, aumento, desdobramento and reducao; 2025 capital_social). Fixture lines are byte-exact (cp1252): the header plus the rows of Itau 60.872.504/0001-23, Petrobras 33.000.167/0001-01, Natura &Co 32.785.497/0001-97 (registration cancelled 2025-07-01, by incorporation) and BRF 01.838.723/0001-27 (BRFS3 trading ended 2025-09-22).

Every statement was measured on 2026-11-07 against a real response unless marked *(not verified)*. Recon was cut short by a usage-limit stop; gaps are listed under Open questions.

## 1. Access
- HTTPS file tree https://dados.cvm.gov.br/dados/CIA_ABERTA/ (nginx autoindex behind Cloudflare). No auth. A generic UA worked; no blocking was seen.
- Headers: `Last-Modified`, `ETag` (nginx style, mtime-hex/size-hex) and `Content-Length`. `If-None-Match` and `If-Modified-Since` both return **304**. `Accept-Ranges: bytes` gives 206, so single zip members can be read without the whole zip (central directory first, then member ranges). Cloudflare `Cache-Control: max-age=14400`.
- The autoindex shows times in BRT (UTC-3), and Last-Modified is in GMT.
- CKAN API (`/api/3/action/package_list`, `package_show`): *(not verified)*.
- Regeneration seen: the current year and the four years before it were all rewritten on 2026-11-01 (a Sunday, about 07:00-08:50 BRT), so the cycle looks weekly *(cadence inferred from one listing)*. Older years are frozen, e.g. 2021 last written 2025-12-28 and 2020 on 2024-12-29. So a year is rewritten for about 5 years after it ends.

## 2. Datasets
| dataset_id | history | URL |
|---|---|---|
| fre_cia_aberta | 2010-2026 (6-10 MB zips) | DOC/FRE/DADOS/fre_cia_aberta_YYYY.zip; DOC/FRE/META/meta_fre_cia_aberta.zip (about 50 dictionaries) |

## 3. Layout
- The index has the same columns as the FCA index (...;DT_RECEB;LINK_DOC).
- **capital_social** columns: ID_Capital_Social;Tipo_Capital;Data_Autorizacao_Aprovacao;Valor_Capital;Prazo_Integralizacao;Quantidade_Acoes_Ordinarias;Quantidade_Acoes_Preferenciais;Quantidade_Total_Acoes. It exists in 2022, 2023 and 2025.
- History members, present in 2022:
  - **capital_social_aumento**: Data_Deliberacao, Orgao_Deliberacao_Aumento, Data_Emissao, Valor_Total_Emissao, share quantities (ON/PN/Total), Preco_Emissao, Fator_Cotacao, Tipo_Subscricao, Forma_Integralizacao;
  - **capital_social_desdobramento**: Data_Aprovacao, Tipo_Evento, share quantities (ON/PN/Total) before and after;
  - **capital_social_reducao**: Data_Deliberacao, Data_Reducao, Valor_Total_Reducao, Valor_Restituido_Por_Acao, Forma_Restituicao;
  - each of the three has a _classe_acao child table.
- Other 2025 members: posicao_acionaria (+_classe_acao), distribuicao_capital (free float), outro_valor_mobiliario, participacao_sociedade, remuneracao tables, transacao_parte_relacionada, and others.

## 4. Quirks
- **Layout change:**
  - the 2022 zip has aumento (1.26 MB), desdobramento and reducao;
  - in 2023 the same members are nearly empty (12 KB, 670 B, 635 B);
  - **the 2025 zip has none of them**.
  - So capital-change history exists in open data only for FREs with DT_REFER up to 2022/2023. The likely cause is the new FRE under Res. CVM 59 *(not verified)*.
- Whether the sub-tables keep only the latest version, as FCA does: *(not verified)*.
- Encoding is cp1252, ';' separator.

## 5. Identity fields
CNPJ and CVM_CODE. There are no tickers in the capital tables.

## 6. Ephemerality
Persistent yearly files.

## 7. Parsed (2026-11-07)
- `ingest/cvm_fre.py` parses the index into staging `document` (73,421 versions) and `capital_social` into staging
  `capital_social` (45,661 rows, 0 quarantined). Other members are not parsed; some hold personal data.
- `capital_social` exists in every year 2010-2026, with ON, PN and total quantities. Each yearly zip keeps only the
  latest version of each company's FRE; the index lists every version with its DT_RECEB.
- **Counts are whole shares** (Itaú 2016: 6,582,307,543; Petrobras 13,044,496,930). Against the nearest DFP/ITR count
  with a known unit (2020-), 2,161 of 2,251 agree within 30 %. The rest are real capital changes, plus 5 at a factor
  of about 1,000 where the DFP-side unit inference looks wrong (Iguatemi, SmartFit).
- A document may list several `Capital Integralizado` rows, one per approval; the latest approval is the current
  one. They feed core `share_count` as form `fre` (ADR-0021).

## 8. Open questions
- Tipo_Evento domain (desdobramento, grupamento or bonificacao).
- Number and decimal formats.
- Whether 2024+ has any replacement for capital history.
