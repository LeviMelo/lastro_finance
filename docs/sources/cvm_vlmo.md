# cvm_vlmo - CVM: VLMO (valores mobiliarios negociados e detidos)

**Tier:** P. **Recon date:** 2026-11-07. **Fixture:** `tests/fixtures/cvm_vlmo/vlmo_cia_aberta_2025.csv` (index rows). Fixture lines are byte-exact (cp1252): the header plus the rows of Itau 60.872.504/0001-23, Petrobras 33.000.167/0001-01, Natura &Co 32.785.497/0001-97 (registration cancelled 2025-07-01, by incorporation) and BRF 01.838.723/0001-27 (BRFS3 trading ended 2025-09-22).

Every statement was measured on 2026-11-07 against a real response unless marked *(not verified)*. Recon was cut short by a usage-limit stop; gaps are listed under Open questions.

## 1. Access
- HTTPS file tree https://dados.cvm.gov.br/dados/CIA_ABERTA/ (nginx autoindex behind Cloudflare). No auth. A generic UA worked; no blocking was seen.
- Headers: `Last-Modified`, `ETag` (nginx style, mtime-hex/size-hex) and `Content-Length`. `If-None-Match` and `If-Modified-Since` both return **304**. `Accept-Ranges: bytes` gives 206, so single zip members can be read without the whole zip (central directory first, then member ranges). Cloudflare `Cache-Control: max-age=14400`.
- The autoindex shows times in BRT (UTC-3), and Last-Modified is in GMT.
- CKAN API (`/api/3/action/package_list`, `package_show`): *(not verified)*.
- Regeneration seen: the current year and the four years before it were all rewritten on 2026-11-01 (a Sunday, about 07:00-08:50 BRT), so the cycle looks weekly *(cadence inferred from one listing)*. Older years are frozen, e.g. 2021 last written 2025-12-28 and 2020 on 2024-12-29. So a year is rewritten for about 5 years after it ends.

## 2. Datasets
**The dataset exists in open data.**

| dataset_id | history | URL |
|---|---|---|
| vlmo_cia_aberta | 2018-2026 (79-818 KB zips) | DOC/VLMO/DADOS/vlmo_cia_aberta_YYYY.zip; DOC/VLMO/META/meta_vlmo_cia_aberta.zip |

## 3. Layout
- vlmo_cia_aberta_YYYY.csv (the index): CNPJ_Companhia;Nome_Companhia;Data_Referencia;Versao;Codigo_CVM;Categoria;Tipo;Data_Entrega;Tipo_Apresentacao;Motivo_Reapresentacao;Protocolo_Entrega;Link_Download.
- vlmo_cia_aberta_con_YYYY.csv (12 MB in 2025): CNPJ_Companhia;Nome_Companhia;Data_Referencia;Versao;Tipo_Empresa;Empresa;Tipo_Cargo;Tipo_Movimentacao;Descricao_Movimentacao;Tipo_Operacao;Tipo_Ativo;Caracteristica_Valor_Mobiliario;Intermediario;Data_Movimentacao;Quantidade;Preco_Unitario;Volume.
- The data is aggregated by Tipo_Cargo, not by person *(inferred from the columns)*.

## 4. Quirks
- The 2018 file is small (79 KB), so it is probably a partial year *(not verified)*.

## 5. Identity fields
CNPJ, CVM_CODE. The security is described only in free text; there is no ticker.

## 6. Ephemerality
Persistent.

## 7. Parsed (2026-11-08)
`CvmVlmo` → staging `document` and `movement` (`src/fin/ingest/cvm_vlmo.py`), measured on 2018 and 2025:
- Both members are cp1252 with dot decimals. Quantities are signed integers up to 12 digits (2,416 negative in
  2025); prices and volumes carry 10 decimals.
- Every version is kept in both members: 382 of 5,397 company-months of 2025 have more than one.
- 2018: 415 filings and 3,616 lines (from 2018-12). 2025: 5,833 filings and 63,195 lines. Nothing quarantined.
- Domains (2025):
  - Tipo_Empresa: Companhia, Controladora, Controlada;
  - Tipo_Cargo: five role groups, plus 262 empty;
  - Tipo_Operacao: Crédito, Débito;
  - Tipo_Movimentacao: Saldo Inicial (36,795), then à vista sales and purchases, loans, grants and others.
- **Not parsed (personal data):** `Motivo_Reapresentacao` names people (e.g. "do Conselheiro …", "cônjuge da
  Diretoria …"), and `Descricao_Movimentacao` can too ("POSSE DE CÔNJUGE <name> NO CONSELHO FISCAL").

## 8. Open questions
- None after parsing. The 2018 file holds only 2018-12 (measured); 2018-01…11 are not served.
