## ADR-0016: Corporate events are merged across sources and graded by the price move; adjustment factors are derived from graded events only

**Date:** 2026-11-07. **Status:** active. Implements PLAN §4.3.3 and §4.7 for listed equities and FIIs (`core/events.py`).

**Context.** No primary source gives complete corporate events for free.
- **B3's listed-companies backend** (tier U):
  - its cash history is complete;
  - its stock events start in 2011 and miss some (ITUB 2025-03, SLCE 2023-04, RADL 2023-04: golden_events.md).
- **Yahoo** (tier U) has the splits and bonuses B3 misses, but its dividends are split-adjusted and don't separate
  JCP.
- **CVM IPE** (P) proves events, but as PDFs.

**Decision.**
- **One table, `core.corporate_event`.**
  - Stock events: B3 Supplement (by ISIN) and Yahoo (by ticker valid on the date). They are merged on
    (instrument, ex-date, exact ratio); a B3 BONUS and a Yahoo "split" with the same ratio are one event, and B3's
    type wins.
  - Cash events: B3's cash history, mapped by issuer root and share class (the first word of ESPECI in COTAHIST), and
    Fundos.NET notices (by ISIN, with the delivery minute as `kt_published_at`).
- **B3 factors are read by label:**
  - BONIFICACAO and DESDOBRAMENTO are percents: ratio = 1 + f/100;
  - GRUPAMENTO is new per old: ratio = f;
  - other labels (CIS RED CAP, INCORPORACAO…) are not adjustments.
- **Ex-date** = the first B3 session after the data-com, from the sessions in `price_daily`.
- **Grading of stock events.** For each instrument, ex-date and source group (B3 when B3 reports any that day, else
  Yahoo; never summed across groups), take the raw move = close(last session before) / close(ex) and compare it
  with the net ratio. The move agrees when:
  - it is closer, in log space, to the ratio than to 1, and within a factor of 2 of the ratio; or
  - for ratios within ±20 % of 1, which no daily move can tell from noise, it is within 10 % of the ratio.
- **Status:**
  - `confirmed`: two sources, or B3 plus an agreeing move;
  - `price_only`: one source plus an agreeing move;
  - `candidate`: anything else.
- **Factors.** `derived.adjustment_factor` uses graded events only. Prices before the ex-date are multiplied by
  1/ratio for stock events and by (1 − cash / close of the data-com) for cash. Adjusted prices are computed on read
  (`adjusted_close`) and never stored as truth.

**Evidence (docs/evaluation/2026-11-07-corporate-events.md).**
- Split adjustment alone equals Yahoo's split-adjusted close monthly from 2010 for PETR4, ITUB4, VALE3, BBAS3, ABEV3,
  B3SA3 and SUZB3.
- MGLU3 (2024-02) and LREN3 (2021-03) differ by Yahoo's rights-offering adjustment, which is not modelled.

**Added the same day.** Rights offerings from the B3 Supplement's `subscriptions[]`: factor = theoretical ex-rights
price / cum price, applied only when the subscription price is below the cum price. Identical cash rows are kept
(distinct installments), taken from each issuer's latest run.

**Added: IPE evidence.** Each stock event is matched to the earliest IPE document of its issuer (CNPJ via
`issuer_instrument`):
- the category announces events (Fato Relevante, Aviso aos Acionistas, Comunicado ao Mercado, Assembleia);
- the subject names the event (bonifica / desdobr / grupament);
- it was delivered between 90 days before the data-com and 10 days after the ex-date.

A match adds `cvm_ipe` to the sources, which makes the event confirmed (two sources), and keeps the protocol and
link. A Yahoo "split" whose filing speaks of a bonificação becomes a BONUS. Both ITUB 2025 bonuses match the
filings of golden_events.md.

**Not done.** Mergers and ISIN changes without a B3 event, as event legs (ADR-0019).
