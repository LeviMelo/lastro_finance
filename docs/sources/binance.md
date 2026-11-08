# binance: Binance public bulk data (spot klines)

Recon 2026-11-08. Tier S: an exchange's own record of its own market, used as context. Crypto is scope priority 3
(ADR-0011); the BRL pairs price the crypto ETFs' underlying (HASH11, QBTC11…). Connector `BinanceKlines`
(`src/fin/ingest/binance.py`).

## Access (no login, no key)
- Monthly: `https://data.binance.vision/data/spot/monthly/klines/<SYMBOL>/1d/<SYMBOL>-1d-<YYYY-MM>.zip`, 1–2 KB,
  one headerless CSV, with a `.CHECKSUM` file (sha256 equal to our download for BTCBRL 2026-10).
- Daily: `.../daily/klines/<SYMBOL>/1d/<SYMBOL>-1d-<YYYY-MM-DD>.zip`, used for the current month.
- Listing: `https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?delimiter=/&prefix=data/spot/monthly/klines/<S>/1d/`
  (S3 XML: Key, Size, ETag).
- Depth: BTCBRL from 2020-10 and BTCUSDT from 2017-08. ETHBRL, USDTBRL, SOLBRL and ETHUSDT listings answer too.

## Layout
- 12 columns: open time, O, H, L, C, base volume, close time, quote volume, trades, taker-buy base, taker-buy
  quote, ignore.
- Times are epoch milliseconds in 2020 files and microseconds (16 digits) in 2026 files. The parser reads the unit
  from the digit count.
- A day is the UTC day of the open time.
