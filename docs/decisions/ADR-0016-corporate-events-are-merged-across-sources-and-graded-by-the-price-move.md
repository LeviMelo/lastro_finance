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

**Addendum (2026-11-07): `conflicting`.** The new Yahoo reconciliation (ADR-0022) found that our split adjustment
multiplied ITUB4's prices before 2011-11 by 100.
- Cause: B3 and a CVM filing report a 1:100 reverse split on 2011-11-01. It was simultaneous with a 100:1 split
  (net 1), and the price moved by 1.02, but two sources made the event `confirmed`.
- Rule: when the price contradicts the ratio, the event is `conflicting` whatever the sources say, and it adjusts
  nothing. The price contradicts the ratio when the move is closer to no event than to the ratio, with the ratio
  beyond ±20 % of 1. Adjusting it would put a jump into our adjusted series.
- Result: 57 stock events become conflicting: 926 confirmed, 70 price only, 66 candidates.
- The golden cases are unchanged, and the ITUB4 2011 Yahoo finding is gone.

**Addendum (2026-11-08): every event is decided; the official prices are evidence.**
- **The price check works in BRL, corrected for IPCA.** A currency change (÷1,000 in 1989 and 1993, ÷2,750 in 1994) is
  not an event, and 1986-94 sessions months apart drift 20-80 % a month. Beyond 90 days the move says nothing. This
  alone turned 21 of the 57 `conflicting` events into agreeing ones.
- **Statuses are final.** The applied ones are `confirmed`, `price_only` and `official` (B3 alone, price
  inconclusive). The not-applied ones are `conflicting`, `unpriced` (no session on one side) and `unsupported` (Yahoo
  alone, price inconclusive). `candidate` no longer exists.
- **Re-dating.** A reported ex-date the price disagrees with is moved to the session within 30 days where the price
  did move by the ratio (`ex_date_reported` keeps the source's date); 19 events.
- **`QUOTE_BASIS`.** COTAHIST itself shows 991 changes of FATCOT with a continuous quoted price. At each, the price
  per share jumps by the factor: a regrouping (MGEL4 2004-06-29: 4.90 per 1,000 to 4.95 per share), or the 1987-89
  mass flag changes. Each is an adjustment, skipped where an applied event of that size is within 5 days.
- **Implied events.** A Yahoo level shift of at least 1.25 can be matched (within 30 % in log) by a one-day move of
  the raw BRL close that our factors leave in place. It becomes a `confirmed` event when a CVM filing announces it,
  or when the move is 3x or more. 10 events: MWET4/MWET3/AZEV4 2005 (1:10,000), BRKM6 2005 (1:1,000), CMIG4
  2007/2009, USIM6 2008, BRAP3 2021 (2:1), MAXR11 2021 (22:1).
- **Result:** 940 confirmed, 71 price only, 39 official, 45 unpriced, 30 conflicting, 4 unsupported, and 990
  QUOTE_BASIS. Golden cases unchanged.
- **Spin-offs** (B3 `CIS RED CAP` issuing another ISIN). The factor is new shares per 100 held (PCAR3 → ASAI3:
  100; SANB → GETT: 25). The parent's earlier prices are scaled by f = 1 - k × the first close of the new line
  (within about 10 sessions) / the parent's cum close, folded into `split_factor`. 22 spin-offs: PCAR3 2021-03-01
  f = 0.140, where Yahoo shows a shift of 7.55. The rest had no priced new line in time (Telebrás 1998).

**Addendum (2026-11-08): payouts B3 lacks.** A Yahoo dividend is added as a cash event (`OTHER_CASH`, sources
`yahoo_chart,cvm_ipe`) when all three hold:
- we hold no cash event of the line within 120 days;
- a CVM IPE filing of the issuer that names a payout was delivered up to 60 days before;
- the amount, converted from Yahoo's split basis, comes from Yahoo.

41 events were added, 34 of them Fras-le 2008-2026 (B3's history stops in 2002). Yahoo alone is never applied.

**Not done.** Mergers and ISIN changes without a B3 event, as event legs (ADR-0019).

**Addendum (2026-11-08): stock events on lines Yahoo does not cover.**
- **Why.** The panel showed month returns of 30x to 230,000x on delisted or old lines: TOYB3 2015, OGXP3 2016,
  BRPR3 2023, JBDU 2013–14, MAPT4 2019. These were regroupings that B3's events backend lacks. The Yahoo-led
  path never sees them, because Yahoo only covers tickers that still trade.
- **The new path (`implied_ipe_events`).** It runs from the Real (1994-07) on. A one-day move of the raw BRL close
  of 3x or more, on a day no factor adjusts, is kept when either:
  - a CVM IPE filing of the issuer announces the regrouping, split or bonus around it (202 events, now reachable
    thanks to the issuer links of ADR-0018); or
  - the move is 10x or more at a conventional ratio (2, 3, 4, 5, 8, 10, 15, 20, 25 … 1,000,000): within 2 % for a
    regrouping, and within 0.5 % for a split, since a collapse also moves prices down (125 events).
  Any large move lies within 2 % of some integer, so the ratio set is what keeps CABLE ONE "1:194" out.
- **Result.** 52,972 events, none quarantined. Golden events 9/9 and the §13.1 portfolio are unchanged. Panel
  month returns beyond +300 % or -90 % fell from 112 to 57; the rest are flagged (`ret_suspect`, ADR-0032).

**Addendum (2026-11-08, later): near-duplicate events.**
- **Detector fix.** The panel's remaining extremes included regroupings counted twice. The implied path had added
  an event days after one B3 reports (CBEE3: 1:40000 on 2016-01-15, then 1:39991 on 01-29). Its candidates now
  give way to any known stock event of the line within 45 days.
- **`resolve_clusters`.** Applied stock events of one line within 10 days are now checked as one price move.
  When their combined factor misses the move by more than 1.5x, the fewest events that fit it within 0.3 (log)
  stay applied and the others become `conflicting`. Example: TUPY4 2010 had a 1:1000 regrouping and a 1:1000
  quote-basis change for the same act.
- **Result.**
  - Events: 52,933, with 71 stock events conflicting.
  - Panel month returns beyond +300 % or -90 %: 46 of 82,227 (from 112 at the start of the day).
  - Golden events 9/9 and the §13.1 portfolio are unchanged.
  - What remains is mostly real distress (AMER3 2023, PDGR3, AZUL, GOLL) or ratios every source has wrong
    (BSLI3 2021: B3 10:1, Yahoo 9:1, price ~4:1; TELB4 2011). These stay flagged (`ret_suspect`), not guessed.
