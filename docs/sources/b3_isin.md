# b3_isin: B3's ISIN database

Recon 2026-11-08 (in-app browser, then curl with a browser UA). Connector `B3Isin` (`src/fin/ingest/b3_isin.py`).

## Access (no login)
- Page `https://sistemaswebb3-listados.b3.com.br/isinPage/` (Angular). API: `.../isinProxy/IsinCall/`.
- `GetTextDownload/` (JSON) lists the files with ids and generation times: `geralPt`/`geralEn` (the full database,
  regenerated every evening), `mensalPt`, and `diariosPt` (19 files: the last ~19 business days).
- `GetFileDownload/<base64(id)>` returns a zip. The page itself also calls `GetListEmitterFilter`, `GetDetail`,
  `GetEmitterCode` (search; not used).

## Files
- Full database (2026-11-06): 8.3 MB zip holding EMISSOR.TXT (7.4 MB, 69,803 issuers), NUMERACA.TXT (106 MB,
  428k ISINs; status A 40,964, N 387,369, D 1) and Leiame.pdf (the layout, 38 pages).
- Daily file (2.6 MB): EMISSOR.TXT (full issuer list) and NUMERACA_D.TXT (the day's new and changed ISINs; 1,715
  lines on 2026-10-09).
- EMISSOR: `"code","name","cnpj","yyyymmdd"`, UTF-8. The date is 20180628 for issuers migrated to the current system.

## Findings
- **Cancelled codes and ISINs are deleted.** KROT (Kroton, now COGN), CTIP (Cetip), TBLE (Tractebel, now Engie)
  and their share ISINs are absent. Only the daily change files record a cancellation, and they are served for
  ~19 days, so they are archived daily (`ephemeral`).
- Codes still registered resolve companies that left trading: SMLE → 15912764000120 (Smiles), BRPR →
  06977751000149, RUMO → 71550388000142, GETT → 10440482000154, PPLA → 15073274000188.

## Storage
Members are stored as deltas of the previous file of the same kind (constant locator, ADR-0014). The full database
is fetched weekly.
