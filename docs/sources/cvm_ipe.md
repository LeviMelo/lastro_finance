# cvm_ipe - CVM: IPE (documentos eventuais)

**Tier:** P. **Recon date:** 2026-11-07. **Fixture:** `tests/fixtures/cvm_ipe/ipe_cia_aberta_2025.csv` (about 294 KB) and three Itau PDFs (580 KB). Fixture lines are byte-exact (cp1252): the header plus the rows of Itau 60.872.504/0001-23, Petrobras 33.000.167/0001-01, Natura &Co 32.785.497/0001-97 (registration cancelled 2025-07-01, by incorporation) and BRF 01.838.723/0001-27 (BRFS3 trading ended 2025-09-22).

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
| ipe_cia_aberta | 2003-2026 (228 KB-2.3 MB zips, one CSV member) | DOC/IPE/DADOS/ipe_cia_aberta_YYYY.zip; DOC/IPE/META/meta_ipe_cia_aberta.txt |

## 3. Layout
- Columns (identical in 2003 and 2025): CNPJ_Companhia;Nome_Companhia;Codigo_CVM;Data_Referencia;Categoria;Tipo;Especie;Assunto;Data_Entrega;Tipo_Apresentacao;Protocolo_Entrega;Versao;Link_Download.
- The 2025 member is 20.2 MB uncompressed.

## 4. Quirks
- Encoding is cp1252 (decoded without error for 2023-2026; 187,637 rows), ';' separator.
- The years 2003-2014 were written once, in 2021.
- **Data_Entrega is a date only** (`2025-02-05`, 10 characters in all 187,637 rows of 2023-2026), as is Data_Referencia. There is no time of day, so the knowledge time is day-granular (use end of day or the fetch time for intraday ordering). `Versao` 1-5+ and `Tipo_Apresentacao` AP / RE (espontanea) / RC (por exigencia); Protocolo_Entrega repeats across versions (`...-22` v1, v2 in a later row).
- Categoria domain (top, 2023-2026): Valores Mobiliarios negociados e detidos (35k), Assembleia (33k), Reuniao da Administracao (30k), Comunicado ao Mercado (25k), Dados Economico-Financeiros (23k), Fato Relevante (10.3k), Aviso aos Acionistas (6.8k), Relatorio Proventos (3.2k), Calendario de Eventos Corporativos (3.4k). `Assunto` is free text (often empty for Assembleia); events are best found by Assunto keywords plus Categoria.
- **Link_Download works** (e.g. `https://www.rad.cvm.gov.br/ENET/frmDownloadDocumento.aspx?Tela=ext&descTipo=IPE&CodigoInstituicao=1&numProtocolo=1330897&numSequencia=855623&numVersao=1`, browser UA, no cookie, no Referer): HTTP 200, body is a **PDF** (sizes 73-435 KB measured over 15 documents), but `Content-Type: text/html` and `Content-disposition: attachment; filename=019348000101011.pdf` (the filename is the same for different documents). Check the `%PDF` magic, not the header. Some PDFs are text-based (pdftotext works), some have no embedded accents in the text layer (diacritics dropped by pdftotext on several).
- **Transient empty shell**: 4 of 16 first requests (and 1 further retry) returned a 4.3 KB HTML page titled "ENET Download de Documento" with an empty form and no document, status 200. A retry after 2 s returned the PDF. Plain `curl` and urllib behaved the same. Retry up to 3-4 times, 1-2 s apart, until the body starts with `%PDF`; never store the shell.
- Link_Download holds numProtocolo / numSequencia (not the Protocolo_Entrega string); keep both.

## 5. Identity fields
CNPJ, CVM_CODE. Protocolo_Entrega with Versao serves as the document id.

## 6. Ephemerality
Persistent.

## 7. Open questions
- Whether old (2003-2014) Link_Download documents still resolve.
- Whether the empty shell depends on server-side load or on the document (the same URL succeeded on retry).

## 8. Parsed (2026-11-07, `ingest/cvm_ipe.py`)
- 749,235 document rows 2003-01-06 → 2026-10-30; the header is identical in every year. 246,855 rows have no
  protocol (most of the older years, and some recent ones).
- Used as evidence for stock events (ADR-0016): subject keywords `bonifica`, `desdobr`, `grupament`; ITUB's bonus
  Fato Relevante of 2025-02-05 has subject "Bonificação de Ações" and no type or species.
