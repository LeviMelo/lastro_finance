# Resolved open questions

Rows moved whole from `OPEN_QUESTIONS.md` when answered, with the answer and where it is recorded.

| # | question | status | where it came from |
|---|---|---|---|
| 5 | Where are B3's reference curves (DI × pré, DI × IPCA) published since the old TxRef page went 404, and how long is their window? | resolved -> docs/sources/b3_reference_rates.md (2026-11-07): `pesquisapregao` TS files (TaxaSwap.txt, every curve) from 2000-01-14, archived daily by `b3_pesquisapregao`; the web CSV covers 2026-10-05 onward only. | docs/sources/b3_reference_rates.md |
| 6 | How many past days does B3's instrument registry (InstrumentsConsolidated) serve? | resolved -> docs/sources/b3_instruments.md (2026-11-07): the file route serves 2025-06-10 onward (356 files), backfilled the same day; BDI JSON D-21; pesquisapregao IN (BVBG.028) from 2018-01-02. Whether the start rolls: OQ-19. | PLAN §4.4 |
| 12 | Start date of the personal ledger (first transaction). | resolved -> ADR-0011 (2026-11-07): the first transaction is in 2026. | PLAN §12.3 |
| 13 | Do offshore and crypto holdings exist or are they anticipated? | resolved -> ADR-0011 (2026-11-07): not now; the holdings will be stocks, FIIs, ETFs and Tesouro Direto. | PLAN §12.4 |
