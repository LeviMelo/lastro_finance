# pyield_data — third-party mirror: ANBIMA government-bond rates, B3 futures, NTN-B VNA

**Tier:** S (mirror of P data, verified on overlap; ADR-0010). **Recon date:** 2026-11-07. **Fixture:** none (the
archived release files are the evidence; 0.1–10 MB).

## 1. Access
- `https://github.com/crdcj/pyield-data/releases/latest/download/<name>.parquet` (302 to GitHub's object store, 200).
  Release tag `data-YYYY-MM-DD`, rebuilt daily by a GitHub Action of the author of the `pyield` library (PyPI 0.63.0,
  2026-11-03, MIT). **The data repository has no licence file**; ANBIMA's and B3's terms govern the underlying data.
- Archived on demand (`fin ingest pyield_data --mode backfill`), not daily.

## 2. Datasets (release of 2026-11-07)
| dataset_id | rows | range | content |
|---|---|---|---|
| `anbima_tpf` | 78,825 | **2020-01-02 → 2026-11-06**, 1,707 days | data_referencia, titulo, codigo_selic, data_base, data_vencimento, pu, taxa_compra, taxa_venda, taxa_indicativa |
| `b3_futures` | 518,505 | 2018-01-02 → 2026-11-06 | DI1, DDI, FRC, FRO, DAP, DOL, WDO, IND, WIN: open interest, trades, prices, settlement (`AdjstdQt`, `AdjstdQtTax`) |
| `vna_ntnb` | — | not inspected | NTN-B VNA |

## 3. Verification
- Against our own ANBIMA `ms*.txt` files (2026-10-29 … 11-06, 50 bonds a day): 0 unmatched bonds, rates equal to
  3e-17, PU equal. Example: LTN 2027-04-01 on 2026-10-29, PU 948.687824 and indicative rate 13.7549 % in both.
- The mirror drops ANBIMA's standard deviation, interval and `Criterio` columns. Rates are fractions (0.137549).
- Rows before 2020 are not in the release. pyield fetches them from an ANBIMA host for members only (not public).

## 4. Use
- Bond rates 2020-01-02 → 2026-10-28 enter as tier-S facts. From 2026-10-29 our ANBIMA archive is primary and the
  mirror is a continuous cross-check. Futures: same horizon as B3's PR files (the PR backfill is OQ-20).
