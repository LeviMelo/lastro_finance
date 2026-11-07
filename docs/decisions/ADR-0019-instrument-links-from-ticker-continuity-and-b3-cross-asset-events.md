## ADR-0019: Instruments are linked by ticker continuity across an ISIN change and by B3 events that issue another asset; only same-class events adjust prices

**Date:** 2026-11-07. **Status:** active. First edges of PLAN §4.3.3's event graph (`core/links.py`).

**Context.** An ISIN change makes a new instrument (ADR-0015). B3's Supplement lists stock events with an `isinCode`
(the class with the right) and an `assetIssued`, and 249 of its 1,055 events issue a *different* ISIN:
- a bonus in another class (CYRE 2025-12: PN shares to ON holders);
- a spin-off (`CIS RED CAP`), an incorporation (`INCORPORACAO`), a full redemption (`RESG TOTAL RV`).

The first event build applied every BONIFICACAO as a split of the receiving class, which is wrong when the shares
issued are of another class.

**Decision.**
- **Only same-class events adjust prices.** A B3 stock event adjusts the price of its `isinCode` only when
  `assetIssued` is empty or equal to it.
- **`core.instrument_link`** holds the other edges:
  - `ticker_continuity`: one ticker trades under ISIN A until a session and under B within the next 5 sessions, and
    A never trades again. The price ratio across the switch is kept.
  - B3 cross-asset events, from the receiving instrument to the issued one, with B3's factor as written; its unit
    depends on the label.
- Links do not adjust anything yet: they let a holding or a backtest follow a share across them.

**Measured (2026-11-07).** 170 links: 55 spin-offs, 47 ticker continuities, 35 bonuses in another class,
26 incorporations, 7 others. The golden cases are unchanged (`scripts/check_golden_events.py`: all OK).

**Not done.** Mergers that change ticker and ISIN at once without a B3 event (Itaú Holding ITAU4 to ITUB4,
2009) need the CVM IPE filings.
