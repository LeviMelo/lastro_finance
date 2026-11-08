## ADR-0021: Valuation is a point-in-time catalog macro over share counts, prices and statements

**Date:** 2026-11-07. **Status:** active. `valuation(d)` in `catalog.duckdb` (`fin/catalog.py`).

**Context.** Market cap, P/L and P/VP need share counts, prices and statements, each as known on the date. Storing
them daily would copy what the zones already hold (ADR-0014, ADR-0017).

**Decision.** `valuation(d)` is a macro computed on read, one row per issuer:
- **Market cap.** The latest `share_count` with a known unit that CVM had received by `d`. Outstanding shares
  (paid in − treasury) per class × the last standard-lot close in the 30 days to `d` of the most traded ON and PN
  line, in BRL of the day. The shares grow by that line's bonuses and splits between the count's reference date and
  `d` (1 / `split_factor`). Null when a class with shares outstanding has no traded line.
- **P/L.** Trailing twelve months of consolidated `net_income_controlling`: the annual figure, or the latest
  year-to-date + the previous annual − the year-to-date a year earlier. Only statements received by `d` count.
- **P/VP.** The latest consolidated controlling equity, as filed (banks) or equity − non-controlling interest (new
  metric `noncontrolling_interest`).
- `share_count` gains `received_on` (knowledge date) and treasury per class.
- **Before 2020, FRE counts.** CVM's DFP/ITR zips have share counts from 2020 only; the 2019 zip has no
  `composicao_capital`. FRE `capital_social` (2010-) states whole shares. Each FRE document becomes a `share_count`
  row of form `fre`, unit 1, with no treasury, dated by its delivery. Valuation prefers DFP/ITR counts, which state
  treasury, and uses FRE only when no DFP/ITR count is known yet.

**Measured (2026-11-07).**
- On 2026-11-06, 284 issuers have a row: 253 market caps, 206 P/L, 238 P/VP.
- Petrobras: R$ 628 bn, P/L 4.7, P/VP 1.31. Itaú: R$ 471 bn, P/L 10.0, P/VP 2.16.
- On 2021-06-30, 224 market caps; Vale was R$ 581 bn.
- With FRE counts: on 2026-11-06, 270 market caps; on 2015-06-30, 148 (Ambev R$ 300 bn, Petrobras R$ 176 bn); on
  2011-06-30, 105. P/L is sparse in 2011 (8 issuers): ITR starts in 2011, so there is no prior-year year-to-date.
- Across Itaú's 103:100 bonus (ex 2025-12-26, count of 2025-09-30), its shares grow 3.0% and its market cap stays
  continuous: R$ 409.8 bn on 12-22, R$ 419.6 bn on 12-30.

**Limits.**
- Before 2020 (FRE counts) treasury shares are not subtracted, so market cap is overstated by the treasury share.
- A PN price stands for all preferred classes (PNA, PNB).
