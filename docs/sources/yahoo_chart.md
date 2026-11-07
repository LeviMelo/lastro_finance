# yahoo_chart — Yahoo Finance chart endpoint (unofficial)

**Tier:** U (PLAN §4.4: cross-check only; facts enter as candidates, ADR-0010). **Recon date:** 2026-11-07.

## 1. Access
- `GET https://query1.finance.yahoo.com/v8/finance/chart/<TICKER>.SA?range=max&interval=1d&events=div|split`: 200,
  no key, browser UA. Undocumented; Yahoo's terms restrict use. One request per ticker.

## 2. What it gives
- Daily OHLC (split-adjusted) and `adjclose`, `events.splits` {date, numerator, denominator, splitRatio}, and
  `events.dividends` {date, amount} from ~2007, **split-adjusted, with no JCP/dividend distinction**.
- `interval=1mo` moves event dates to the month start: never use it for events.

## 3. Verification on B3's misses (OQ-18)
| case | Yahoo |
|---|---|
| ITUB4 bonificações | 2025-03-18, 110:100; 2025-12-26, 103:100 |
| SLCE3 bonificações | 2022-01-03 11:10; 2023-05-09 11:10; 2023-12-14 2:1; 2026-01-02 9:8 |
| RADL3 bonificação | 2023-05-22, 26:25 |
| MGLU3 desdobramento | 2020-10-14, 4:1 |
- Yahoo's dates are ex-dates. Each Yahoo event must be matched to a CVM IPE document (P) before it adjusts anything.
- Other U sources measured the same day: brapi without a token serves only 4 tickers. Fundamentus `proventos.php` and
  Status Invest `companytickerprovents` give cash events with JCP/dividend labels from 1995 and 2007, and no stock
  events.
