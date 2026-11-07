# anbima_calendar — ANBIMA: national holidays (feriados nacionais)

**Tier:** P. **Recon date:** 2026-11-07. **Fixture:** `tests/fixtures/anbima_calendar/feriados_nacionais.xls` (whole file).

## 1. Access
- `GET https://www.anbima.com.br/feriados/arqs/feriados_nacionais.xls` — free, no auth, generic UA works. HTTP 200,
  `application/vnd.ms-excel`, 111104 bytes, `Last-Modified: Fri, 22 Dec 2023 17:54:15 GMT`, IIS 10. TLS server requests renegotiation (curl/schannel handled it).
- Page `https://www.anbima.com.br/feriados/feriados.asp` → 200 HTML. `arqs/feriados_locais.xls` → 404 (guessed name).

## 2. Datasets
| dataset_id | granularity | history depth | cadence | URL |
|---|---|---|---|---|
| feriados_nacionais | day | 2001-01-01 … 2099-12-25 (1264 holidays) | ad hoc (last change 2023-12-22) | above |

## 3. Layout
- BIFF8 `.xls` (Excel 97-2003, codepage 1252), one sheet `Feriados`, 1274 rows × 3 cols. Read with `xlrd`.
- Row 0 header: `Data` | `Dia da Semana` | `Feriado`. Rows 1–1264: Excel date serial (datemode 0), weekday name pt-BR, holiday name.
- Footer: row 1265 `Fonte: ANBIMA`, then 4 numbered notes (rows 1267–1273): Quinta-feira Santa is a business day since 2000 (Res. 2.516);
  elections excluded; last business day of year has no public service but is not listed; municipal holidays excluded —
  "critério: feriados em que não há sensibilização das Reservas Bancárias".
- Sample: `2001-01-01 | segunda-feira | Confraternização Universal`; `2026-11-20 | sexta-feira | Dia Nacional de Zumbi e da Consciência Negra`.

## 4. Quirks
- 12 holidays/year 2001–2023, 13/year from 2024 (Consciência Negra, 20/11, Lei 14.759/2023).
- Weekend holidays ARE listed (e.g. 2001-04-21 Saturday) — business-day logic must still exclude weekends independently.
- One name has a trailing space (`'Confraternização Universal '`, 1 row): strip names.
- Parser must stop at the first non-date cell in column A (footer text).
- Future years are a projection; a law change rewrites them → version the file by sha256 and re-fetch periodically (Invariant 9).

## 5. Identity fields
None (calendar reference).

## 6. Ephemerality
Not ephemeral: whole history in one file. But edits overwrite in place → archive each new sha256.

## 7. Open questions
- Is a B3 trading calendar needed where it differs (e.g. B3-only closures)? *(not verified)*
- History before 2001 (DU counting for older bonds) not in this file.
