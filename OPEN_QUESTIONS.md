# OPEN_QUESTIONS.md

Unresolved questions only. **Append here rather than inventing an answer silently.** When one is resolved, the
answer goes to an ADR or an evaluation entry, and the row moves whole and annotated to
`docs/history/open_questions_resolved.md`. Cite a row as `OQ-N`.

Status: `open` · `measuring` · `owner` (the owner's decision, PLAN §12) · `resolved -> <where>`

| # | question | status | where it came from |
|---|---|---|---|
| 1 | Where does B3's trading calendar differ from ANBIMA's? `is_b3_trading_day` stays null until B3 sessions are observed (COTAHIST dates, BDI `workdays`). | open | ADR-0006 |
| 2 | Plain partitioned Parquet with explicit bitemporal columns, or DuckLake? PLAN §4.2 asks for a spike; default is plain Parquet. | open | PLAN §4.2 |
| 3 | Is there a long-history route for B3 settlements and open interest before 2026-10-07 (BDI serves 21 business days)? Candidates: `pesquisapregao` BVBG.086 files, Internet Archive. | measuring | docs/sources/b3_settlement_prices.md |
| 4 | Is there a free long-history route for ANBIMA's government-bond indicative rates before 2026-10-29? Candidates: ANBIMA Data, Internet Archive; Tesouro Transparente gives Tesouro's own rates, not ANBIMA's. | measuring | docs/sources/anbima_titulos_publicos.md |
| 5 | Where are B3's reference curves (DI × pré, DI × IPCA) published since the old TxRef page went 404, and how long is their window? Ephemeral until shown otherwise; not archived yet. | measuring | docs/sources/b3_reference_rates.md |
| 6 | How many past days does B3's instrument registry (InstrumentsConsolidated) serve? Not yet reconned; possibly ephemeral. | measuring | PLAN §4.4 |
| 7 | CNPJ ↔ ticker history before ~2018: FCA `valor_mobiliario` has empty tickers in 2010. Which source fills the gap (COTAHIST ISIN ↔ ticker plus the CVM registry)? | open | docs/sources/cvm_fca.md |
| 8 | Share-count history after 2023: FRE's capital-change tables are nearly empty in 2023 and gone in 2025; `capital_social` remains. Is that enough for share-count continuity checks (PLAN §4.7.3)? | open | docs/sources/cvm_fre.md |
| 9 | Odd-lot tickers (`XXXX3F`): modelled as a market segment of the same instrument (PLAN §4.3.2 default)? To decide with the COTAHIST parser. | open | PLAN §4.3.2 |
| 10 | Paid sources: is any budget acceptable (ANBIMA Feed, a B3 data vendor), or strictly free sources? | owner | PLAN §12.1 |
| 11 | Brokers, banks and exchanges used now and in the past (to scope statement parsers). | owner | PLAN §12.2 |
| 12 | Start date of the personal ledger (first transaction). | owner | PLAN §12.3 |
| 13 | Do offshore and crypto holdings exist or are they anticipated? | owner | PLAN §12.4 |
| 14 | Does intraday data matter beyond archiving what is free? Default: no. | owner | PLAN §12.5 |
| 15 | Reinvestment assumption for total-return series. Default: ex-date close. | owner | PLAN §12.6 |
| 16 | Is a GUI wanted later? Default: CLI plus exported reports. | owner | PLAN §12.7 |
