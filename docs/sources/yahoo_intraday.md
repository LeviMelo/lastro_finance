# yahoo_intraday — Yahoo Finance 5-minute bars

**Tier:** U (unofficial; PLAN §4.4: context and cross-check, never a sole source of a fact). **Recon date:** 2026-11-07.
**Fixture:** `tests/fixtures/yahoo_intraday/`.

## 1. Access
- `GET https://query1.finance.yahoo.com/v8/finance/chart/<SYMBOL>?interval=5m&period1=<unix>&period2=<unix>`, browser
  UA, no key. Symbols: `PETR4.SA`, `^BVSP`, `BRL=X`. Undocumented; Yahoo's terms restrict use (personal use, ADR-0012).

## 2. Depth (measured on PETR4.SA, 2026-11-07)
| interval | served back to | bars |
|---|---|---|
| 1m (`range=7d`) | 2026-10-28 (~8 trading days) | 2,938 |
| 5m (`range=60d`) | 2026-08-12 (~60 trading days) | 5,040 |
| 60m (`range=730d`) | 2023-12-05 | 5,105 |

No free official intraday exists: B3's BDI `TickByTick*` tables answer errors on every date probed
(docs/sources/b3_instruments.md §7); B3 UP2DATA is paid and for legal persons only.

## 3. Layout
- `chart.result[0]`: `meta` (`symbol`, `currency` BRL, `exchangeTimezoneName` America/Sao_Paulo, `dataGranularity` 5m),
  `timestamp[]` (bar start, Unix UTC), `indicators.quote[0]` {open, high, low, close, volume}.
- Prices are single-precision floats printed as doubles (`45.189998626708984` = 45.19); parsed rounded to 4 decimals.
- The session's last bar can carry volume 0.

## 4. Archive policy
- Daily: 120 most traded shares/units + 60 most traded FIIs (COTAHIST, last 90 days, by volume), `^BVSP`, `BRL=X`.
- Window: from the start of the last archived day to now (≤ 55 days back), so runs barely overlap; the overlap is
  removed in staging (ADR-0014). About 200 requests a day at 1 request/s.
