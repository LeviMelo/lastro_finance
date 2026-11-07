# OPEN_QUESTIONS.md

Unresolved questions only. **Append here rather than inventing an answer silently.** When one is resolved, the
answer goes to an ADR or an evaluation entry, and the row moves whole and annotated to
`docs/history/open_questions_resolved.md`. Cite a row as `OQ-N`.

Status: `open` · `measuring` · `owner` (the owner's decision, PLAN §12) · `resolved -> <where>`

| # | question | status | where it came from |
|---|---|---|---|
| 1 | Where does B3's trading calendar differ from ANBIMA's? Measured 2001–2025: B3 never trades on an ANBIMA non-business day, and skips 287 ANBIMA business days (24/12, 31/12, 09/07, 25/01, 20/11 before 2024, the 2014 World Cup opening…) (docs/sources/b3_cotahist.md). Still to do: fill `is_b3_trading_day` from observed sessions, and decide how future B3 closures are known before they happen. | measuring | ADR-0006 |
| 2 | Plain partitioned Parquet with explicit bitemporal columns, or DuckLake? PLAN §4.2 asks for a spike; default is plain Parquet. | open | PLAN §4.2 |
| 3 | B3 settlements and open interest: `pesquisapregao` PR files (BVBG.086) give them from 2018-01-02 (archived daily since 2026-11-07; backfill is OQ-20). Before 2018: does COTAHIST's TPMERC 050/060 carry futures settlements, or is there no free route? | measuring | docs/sources/b3_settlement_prices.md |
| 4 | Is there a free long-history route for ANBIMA's indicative rates (bonds, debentures, ETTJ, VNA) before 2026-10-29? ANBIMA Data needs a login (401) and points to the paid Feed; the Internet Archive holds 85 daily bond files of 2012–2018 (~5% of days), replay not verified. Tesouro Transparente gives Tesouro's own rates, not ANBIMA's. | measuring | docs/sources/anbima_titulos_publicos.md |
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
| 17 | PETR4 on 2026-11-06: B3's TradeInformationConsolidated has 400,000 more shares (R$ 18.1 M, ~R$ 45.29/share) than COTAHIST, with the same trade count. Which trades does one file count and the other not? | open | docs/sources/b3_cotahist.md |
| 19 | Is 2025-06-10, the oldest date of B3's InstrumentsConsolidatedFile / TradeInformationConsolidatedFile, a fixed start or a rolling ~17-month window? Re-probe 2025-06-10 in a later session. | open | docs/sources/b3_instruments.md |
| 20 | Disk budget: backfill PR files 2018– (~10–15 GB, already compressed) and archive the daily BDI PDF (~32 MB/day; served back to 2022-03; the only B3-official index-composition history)? The host had 50 GB free on 2026-11-07. | owner | docs/sources/b3_settlement_prices.md |
| 21 | B3 fixed-income history: `drp.b3.com.br/Web/HistoricoRF` (before 2025-12-11) and the BDI fixed-income tables with an ~18-month window (DebenturesBusiness, Trade, SaleOff, Stock) are not explored or backfilled. | open | docs/sources/b3_instruments.md |
| 18 | B3's structured events backend misses bonificações: ITUB's 10% of 2025-03, SLCE's and RADL's 2023. Is every share-count event recoverable from CVM IPE documents, and how many are missing from B3 overall? | open | docs/sources/golden_events.md |
