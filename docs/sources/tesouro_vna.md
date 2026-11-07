# tesouro_vna — Tesouro Nacional: VNA of NTN-B and NTN-C (monthly)

**Tier:** P. **Recon date:** 2026-11-07.

## 1. Access
- NTN-B `https://thot-arquivos.tesouro.gov.br/publicacao/53360`; NTN-C `.../publicacao/45833`. GET 200 xlsx (HEAD
  405). The file is overwritten at each update; every version is kept (sha256).

## 2. Content (2026-11-07)
| dataset_id | rows | range | last value |
|---|---|---|---|
| `vna_ntnb` | 316 monthly | 2000-07-15 (1000) → 2026-10-15 | 4766.335112 |
| `vna_ntnc` | 317 monthly | 2000-07-01 (1000) → 2026-11-01 | 6769.735230; one column per maturity group |

## 3. Verification
- NTN-B: 1000 × IPCA(m−1) / 1614.62 (IPCA of Jun-2000): 1000 × 7695.82 / 1614.62 = 4766.3351. Intra-month with
  ANBIMA's projection, 4766.3351 × 1.0021^(du/21): du 10 → 4771.098829 (ANBIMA 2026-10-29: 4771.098828); du 11 →
  4771.575463 (ANBIMA 2026-10-30: 4771.575461).
- NTN-C: 1000 × IGP-M / 183.745 (IGP-M of Jun-2000) reproduces 2026-11-01 exactly. The intra-month day count is not
  pinned (two data points).
- **Rule measured on the whole file (2026-11-07):** NTN-B VNA = trunc(1000 × IPCA index(m−1) / 1614.62, 6 dp) with
  IBGE's index (SIDRA 1737 v2266): exact on 315 of 316 months. 2014-02-15 (2376.026557) needs a Jan-2014 index of
  3836.38 where IBGE serves 3836.37 (a revision or a different print; not resolved).
- Workbook quirks: numbers are floats written with 17 digits (1051.9850879999999 for 1051.985088); NTN-C 2018-01-01
  is a pt-BR text cell ` 3.580,282456`; the 2002/2006 group reads 0 after 2006-12 (no VNA). Parsed into
  `series_observation` as `tesouro_vna:NTN-B`, `tesouro_vna:NTN-C/<maturities>` (ADR-0013).
- The monthly VNA is therefore closed from 2000. ANBIMA's projected daily VNA before 2026-10-29 is recomputable only
  where a projection is known (ANBIMA's own projections are served latest-only).
