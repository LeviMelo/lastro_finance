## ADR-0021: Valuation is a point-in-time catalog macro over share counts, prices and statements

**Date:** 2026-11-07. **Status:** active. `valuation(d)` in `catalog.duckdb` (`fin/catalog.py`).

**Context.** Market cap, P/L and P/VP need share counts, prices and statements, each as known on the date. Storing
them daily would copy what the zones already hold (ADR-0014, ADR-0017).

**Decision.** `valuation(d)` is a macro computed on read, one row per issuer:
- **Market cap.** The latest `share_count` with a known unit that CVM had received by `d`. Outstanding shares
  (paid in − treasury) per class × the last standard-lot close in the 30 days to `d` of the most traded ON and PN
  line, in BRL of the day. Null when a class with shares outstanding has no traded line.
- **P/L.** Trailing twelve months of consolidated `net_income_controlling`: the annual figure, or the latest
  year-to-date + the previous annual − the year-to-date a year earlier. Only statements received by `d` count.
- **P/VP.** The latest consolidated controlling equity, as filed (banks) or equity − non-controlling interest (new
  metric `noncontrolling_interest`).
- `share_count` gains `received_on` (knowledge date) and treasury per class.

**Measured (2026-11-07).**
- On 2026-11-06, 284 issuers have a row: 253 market caps, 206 P/L, 238 P/VP.
- Petrobras: R$ 628 bn, P/L 4.7, P/VP 1.31. Itaú: R$ 471 bn, P/L 10.0, P/VP 2.16.
- On 2021-06-30, 224 market caps; Vale was R$ 581 bn.

**Limits.**
- CVM's zips have `composicao_capital` from 2020 only; the 2019 DFP zip has no such member. So valuation starts in
  2020. FRE `capital_social` (2010–) is the candidate source for earlier years.
- A bonus or split between the share-count filing and `d` is not applied yet.
- A PN price stands for all preferred classes (PNA, PNB).
