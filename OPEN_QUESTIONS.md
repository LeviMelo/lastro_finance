# OPEN_QUESTIONS.md

Unresolved questions only. **Append here rather than inventing an answer silently.** When one is resolved, the
answer goes to an ADR or an evaluation entry, and the row moves whole and annotated to
`docs/history/open_questions_resolved.md`. Cite a row as `OQ-N`.

Status: `open` · `measuring` · `owner` (the owner's decision, PLAN §12) · `resolved -> <where>`

| # | question | status | where it came from |
|---|---|---|---|
| 1 | Where does B3's trading calendar differ from ANBIMA's? Measured 2001–2025: B3 never trades on an ANBIMA non-business day, and skips 287 ANBIMA business days (24/12, 31/12, 09/07, 25/01, 20/11 before 2024, the 2014 World Cup opening…) (docs/sources/b3_cotahist.md). `is_b3_trading_day` is now filled from observed sessions (ADR-0024 addendum). Still open: how future B3 closures are known before they happen. | open | ADR-0006 |
| 2 | Plain partitioned Parquet with explicit bitemporal columns, or DuckLake? PLAN §4.2 asks for a spike; default is plain Parquet. | open | PLAN §4.2 |
| 3 | B3 settlements and open interest: `pesquisapregao` PR files (BVBG.086) give them from 2018-01-02 (archived daily since 2026-11-07; backfill is OQ-20). Before 2018: does COTAHIST's TPMERC 050/060 carry futures settlements, or is there no free route? | measuring | docs/sources/b3_settlement_prices.md |
| 4 | ANBIMA's indicative rates before 2026-10-29: bonds are covered from 2020-01-02 by the `pyield_data` mirror (equal on overlap, ADR-0010); VNA is closed by Tesouro's tables. Still without a free route: bonds before 2020 (85 Wayback days 2012–18; Tesouro morning rates as proxy), debentures (SND trade statistics as proxy; 81 Wayback days 2013–19), CRI/CRA, ETTJ, IMA, projections. Only route: ANBIMA Feed (price not published; members only). | measuring | docs/sources/anbima_titulos_publicos.md |
| 7 | CNPJ ↔ ticker history before ~2018: FCA `valor_mobiliario` has empty tickers in 2010. Which source fills the gap (COTAHIST ISIN ↔ ticker plus the CVM registry)? | open | docs/sources/cvm_fca.md |
| 8 | Share-count history after 2023: FRE's capital-change tables are nearly empty in 2023 and gone in 2025; `capital_social` remains. Is that enough for share-count continuity checks (PLAN §4.7.3)? | open | docs/sources/cvm_fre.md |
| 9 | Odd-lot tickers (`XXXX3F`): modelled as a market segment of the same instrument (PLAN §4.3.2 default)? To decide with the COTAHIST parser. | open | PLAN §4.3.2 |
| 10 | Paid sources: is any budget acceptable? Measured 2026-11-07 (gap matrix): B3 UP2DATA is for legal persons only (R$ 850–1,698/month + per dataset); ANBIMA Feed, B3 UP2DATA On Demand and Economatica publish no price; brapi Pro R$ 1,399.90/year closes no gap that free routes leave open. Asking ANBIMA and B3 for an individual's price is an outward action for the owner. | owner | PLAN §12.1 |
| 11 | Brokers, banks and exchanges used now and in the past (to scope statement parsers). | owner | PLAN §12.2 |
| 14 | Does intraday data matter beyond archiving what is free? Default: no. | owner | PLAN §12.5 |
| 15 | Reinvestment assumption for total-return series. Default: ex-date close. | owner | PLAN §12.6 |
| 16 | Is a GUI wanted later? Default: CLI plus exported reports. | owner | PLAN §12.7 |
| 17 | PETR4 on 2026-11-06: B3's TradeInformationConsolidated has 400,000 more shares (R$ 18.1 M, ~R$ 45.29/share) than COTAHIST, with the same trade count. Which trades does one file count and the other not? | open | docs/sources/b3_cotahist.md |
| 19 | Is 2025-06-10, the oldest date of B3's InstrumentsConsolidatedFile / TradeInformationConsolidatedFile, a fixed start or a rolling ~17-month window? Re-probe 2025-06-10 in a later session. | open | docs/sources/b3_instruments.md |
| 20 | Disk budget: backfill PR files 2018– (measured 11.1 MB a day: ~24 GB) and archive the daily BDI PDF (~32 MB/day; served back to 2022-03; the only B3-official index-composition history)? The futures part of PR is already covered: the pyield mirror equals our PR files on all 14 days held (3,776 contract-days, settlement and open interest identical). What only PR holds is options and the other instruments. The host had 41 GB free on 2026-11-08. | owner: deferred (2026-11-08, "too much; perhaps later") | docs/sources/b3_settlement_prices.md |
| 21 | B3 fixed-income history: `drp.b3.com.br/Web/HistoricoRF` (before 2025-12-11) and the BDI fixed-income tables with an ~18-month window (DebenturesBusiness, Trade, SaleOff, Stock) are not explored or backfilled. | open | docs/sources/b3_instruments.md |
| 18 | B3's structured events backend misses bonificações: ITUB's 10% of 2025-03, SLCE's and RADL's 2023. Is every share-count event recoverable from CVM IPE documents, and how many are missing from B3 overall? Yahoo (U) has all three and a 2025-12 ITUB bonus; archived for 896 tickers (2026-11-07). Next: diff Yahoo against B3 and prove each difference in IPE. | resolved -> ADR-0016 (IPE proof, implied events, every event decided) | docs/sources/golden_events.md |
| 22 | Calendar 1986–2000: build `calendar_day` before 2001 from BCB SGS 12/11 publication days (exact against ANBIMA on 2001–05; Holy Thursdays closed before 2000)? It is a derived record, not an official holiday list; mark those rows so. | answered: yes, `basis` = `bcb_sgs_12` (ADR-0024) | docs/sources/bcb_sgs.md |
| 23 | Free API tokens: Tiingo (offshore prices, 30+ years) and FRED (global context) need a free sign-up with the owner's email. Sign up, or keep offshore on Yahoo (U) and SEC EDGAR? | owner | docs/evaluation/2026-11-07-data-gap-matrix.md |
