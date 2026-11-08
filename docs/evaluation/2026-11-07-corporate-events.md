# Corporate events: 35,056 events, 6/6 golden stock events and the golden cash sum exact; split adjustment equals Yahoo on 7 large caps (2026-11-07)

Regime: commits after 3c3b507; data home `data/`; B3 backfill run 20261107T223008Z-6ede47 (0 errors) plus the
interrupted 20261107T221834Z-737899. Checks: `scripts/check_golden_events.py`, and monthly closes against Yahoo
2010→2026.

| measure | value |
|---|---|
| B3 issuers listed / in COTAHIST's universe / snapshot fetched | 2,110 / ~830 / 676 (675 cash histories, 320 with cash rows) |
| events | 35,056: dividends 8,630; JCP 9,161; FII income 14,842; amortisations 808; rights 392; other cash 64 |
| stock events by status | bonuses 155 confirmed / 71 candidate; splits 189 / 293 price-only / 46; reverse splits 237 / 91 / 77 |
| adjustment factors | 30,292 (instrument, ex-date) |
| golden cases (golden_events.md) | ITUB 2025-12 103:100, ITUB 2025-03 11:10 (Yahoo only), SLCE 9:8, RADL 51:50, EGIE 7:5, BHIA 1:25: all with the filing's ex-date; GRND 2025-12-26 cash 1.086264641 exact |
| split-only adjusted vs Yahoo close, median ratio | 1.0000 for PETR4, ITUB4, VALE3, BBAS3, ABEV3, B3SA3, SUZB3 |
| total-return adjusted vs Yahoo adjclose, median ratio | ITUB4 1.001, VALE3 1.002, WEGE3 1.000, RADL3 1.000, GRND3 1.006, SLCE3 0.985, BBAS3 0.979, PETR4 0.972 |

**Explained differences.**
- RENT3 −3.3 %: B3's 3.85 % bonus of 2025-12-30 (confirmed by the price move) is absent from Yahoo.
- MGLU3 +6.3 % (2024-02) and LREN3 +0.8 % (2021-03): Yahoo adjusts for rights offerings that B3's Supplement does
  not list for them.
- KNRI11 +10 %: FII distributions before 2016-11 are missing. Fundos.NET starts then, and B3's company list does not
  carry funds.

**Found on the way.**
- Identical cash rows are distinct installments: GRND's two 0,221690166 payments collapsed into one until the cash
  history was staged whole and taken from each issuer's latest run.
- Small bonuses (5 %) sit inside one day's noise, so the price test passes them within 10 % of the ratio. Reverse
  splits of distressed issuers keep falling (moves 1.15–1.8× the ratio); the test needs only "closer to the ratio
  than to no event, within 2×".
- A full manifest read on every fetch (delta base, dedup, conditional request) dropped a backfill to 0.2 request/s;
  lookups are now cached per run, and it is back at 1/s.

**After IPE evidence and the same-class rule (ADR-0016, ADR-0019).**
- Stock events (bonuses, splits, reverse splits): 1,119.
  - 949 confirmed, 828 of them by an IPE filing;
  - 70 price-only;
  - 100 candidates.
- Both ITUB 2025 bonuses are matched to the exact Fato Relevante protocols of golden_events.md
  (`scripts/check_golden_events.py`).
