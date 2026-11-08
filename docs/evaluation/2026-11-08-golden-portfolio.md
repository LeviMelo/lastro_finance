# Golden portfolio (PLAN §4.8.4 / §13.1), 2026-11-08

`scripts/check_golden_portfolio.py`: the 17-stock reference portfolio, buy-and-hold from 2025-10-02 to 2026-10-16,
using our adjusted series (`price_adjusted`: splits, spin-offs, cash reinvested at the ex-date close).

| | ours | plan (Yahoo estimate) |
|---|---|---|
| total return | +37.38 % | +37.2 % |
| price return | +28.69 % | +28.5 % |
| Ibovespa (points) | +42.71 % | +42.4 % |
| CDI (SGS 12 compounded) | +14.99 % | +14.9 % |

- **First run:** ABEV3's total return equalled its price return (+41.16 %), so no dividends were counted.
- **Cause:** B3's cash-history endpoint returns nothing for a trading name containing "/" ("AMBEV S/A"; "AMBEV SA"
  gives 40 records). The same was true of 9 issuers (Klabin, Light, Cury, Ourofino…), and Eternit had never been
  queried.
- **After the fix:** 572 cash events recovered, and ABEV3 +49.98 %.
- **Events in the window:** the four bonuses in the window (ITUB, RADL, EGIE, SLCE) are all applied.
- **Completeness against Yahoo's dividends:** 21,854 of 21,970 are matched within 5 days. Of the 116 gaps:
  - most are over-the-counter lines (MRSA*B, EQMA3B) that B3's listed history does not cover;
  - 76 are Yahoo alone with no filing, so they are not applied (check `cash_vs_yahoo`);
  - Fras-le's payouts after 2002 are missing at the source, and 34 are proven by CVM filings, so they are added.
