# susep_ettj — ETTJ of each month's last business day, ANBIMA's file republished by SUSEP

**Tier:** S (a regulator's copy of an ANBIMA file; equal to ANBIMA's own on the overlap day, see §4). **Recon date:** 2026-11-08. **Fixtures:** `tests/fixtures/susep_ettj/` (2015-12, 2025-12, 2026-10).

## 1. Access
- Page `https://www.gov.br/susep/pt-br/assuntos/informacoes-ao-mercado/solvencia-supervisao-prudencial/monitoramento-prudencial/capital-minimo-requerido-e-tap/modelo-de-interpolacao-e-extrapolacao-da-ettj` (2022-; the `-1` suffix lists 2015-12 → 2021) links, per month, SUSEP's own parameter file (`resultado_curvas_divulgacao_*`, IGP-M/TR/cupom cambial curves, not fetched) and `curvazero_YYYYMM.txt`.
- File URL by pattern, no login, browser UA: `https://www.gov.br/susep/pt-br/arquivos/arquivos-ettj/<yyyy>/curvazero_<yyyymm>.txt/@@download/file` (`text/plain`, 3.0–3.7 KB). Listed 2026-11-08: **131 months, 2015-12 → 2026-10**, none missing; the month appears in the first days of the next one. `www.susep.gov.br` (old host) times out on TCP:80 and 301s to gov.br on https.

## 2. Layout
ANBIMA's `CurvaZero` txt with `Idioma=US`: same records as `anbima_ettj` §3, but English labels (`1@Group`, `2@Business Day@Indexed@Prefixed@BEI`), `1,008.5` numbers (thousands `,`, decimals `.`), reference-date line still `dd/mm/yyyy` and **bond-error maturities `mm/dd/yyyy` in 130 files but `dd/mm/yyyy` in 2025-12-30**: the parser reads the order from the dates (NTN-B matures on the 15th) and refuses a file that does not settle it. In 66 of 131 files the Circular 3.361 vertex at 2,520 du is empty.

## 3. History and measured size
Month-end curves (the date is the last ANBIMA business day, e.g. 2016-01-29, 2025-12-30): 131 distinct dates, 2 curves each (PREFIXADOS, IPCA) → 262 `parameter`, 9,282 `vertex`, 1,310 `circular_vertex`, 4,195 `bond_error` rows; 0 quarantined. Raw 440 KB. Daily ETTJ before 2026-10-29 remains unavailable (`anbima_ettj` §1: window of 6 business days; ANBIMA Data needs a token).

## 4. Cross-check
2026-10-30: SUSEP's English file parses to exactly (all four tables) ANBIMA's own PT file archived the same day (test `test_susep_english_copy_equals_anbima_pt_file_of_the_same_day`).

## 5. Ephemerality
Not ephemeral (files stay); monthly, so `fin ingest susep_ettj` (daily job) asks the last 3 months and skips months held.
