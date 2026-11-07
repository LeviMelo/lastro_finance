## ADR-0015: An exchange-traded instrument is an ISIN with time-ranged tickers; price_daily is per unit in the currency of the day, with an exact fraction to BRL

**Date:** 2026-11-07. **Status:** active. Implements PLAN §4.3.2, §4.3.4 and §4.4 for COTAHIST (`core/equities.py`).

**Decision.**
- **Identity.** An instrument is an ISIN.
  - A B3 internal code (CODISI before 1995-05-15, and a few later) is the same instrument as an ISIN when one ticker
    steps from the code to the ISIN on consecutive sessions, one-to-one: 911 codes linked.
  - Tickers are time-ranged attributes, 1,130 of them reused across instruments. An ISIN change is a new instrument,
    to be linked by corporate events (PLAN §4.3.3).
  - `instrument_id` = `I` + 12 hex of SHA-256 of the primary identifier: stable across rebuilds.
- **Scope of `price_daily`:** standard lot (TPMERC 10) and odd lot (20). Options, termo and forwards are left for
  `settlement_price`.
- **Duplicates:** where a daily file repeats the yearly one, the yearly row is kept. Copies that disagree are counted
  (4 on 2026-11-07).
- **Units.**
  - Prices are per one unit (quoted ÷ FATCOT), exact.
  - The currency is resolved by date, not MODREF: ISO BRB, BRC, BRN, BRE, BRR, BRL.
  - `brl_num` / `brl_den` give BRL per unit of that currency exactly. 1/2,750 has no finite decimal, so BRL prices
    before 1994-07 are derived on read, not stored.
  - The quoted values stay in staging; nothing is stored twice.
- **`asset_class` is provisional.** Share, unit, fund_quota, bdr and right come from ESPECI and CODBDI; old codes
  (PP, OP…) stay `other` until B3's ESPECI table is read.

**Evidence.**
- Currency changeovers, median price ratio across each: 1989-01 1,033; 1993-08 1,002 (inside one `CR$` label);
  1994-07 2,744.
- PETR4 is one instrument from 1986: code PETRACPN, then ISIN BRPETRACNPR6 from 1995-03-27; ticker `PET 4` until
  1998-03-13, then PETR4.
- 2026-11-06 closes equal Yahoo's last 5-minute bar for 172 of 173 shares; the exception is IBOV11, which Yahoo
  scales ×100.

**Alternatives.**
- *Ticker as identity*: rejected. Tickers are reused and renamed (PLAN invariant 4).
- *Store BRL-equivalent prices*: rejected. They would be inexact before 1994, and a stored copy of a derived value.
