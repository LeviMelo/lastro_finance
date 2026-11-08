# nefin — NEFIN-USP: Brazilian risk factors

**Tier:** S. **Recon date:** 2026-11-07. **Fixture:** `tests/fixtures/nefin/` (monthly file in full; daily file head 25 + tail 5 rows).

## 1. Access
- Site was rebuilt (GitHub Pages, `Server: GitHub.com`): the brief's `nefin.com.br/data/risk_factors.html` → 200 but a 273-byte redirect stub to `https://nefin.com.br/data/risk-factors/`. Legacy file paths (`/data/risk_factors/nefin_factors.csv`, `/resources/risk_factors/…`) → 404; `/data/risk-factors/<file>.csv` → 404.
- **Files:** `https://nefin.com.br/nefindata/risk-factors/{nefin_factors,nefin_factors_equally_weighted,nefin_factors_monthly,nefin_factors_equally_weighted_monthly}.csv`, methodology `https://nefin.com.br/nefindata/methodology/nefin_methodology.pdf`. No auth, free ("freely available to academics and practitioners"; licence terms not stated *(not verified)*). `ETag "6ad2c76a-d002c"`, `Last-Modified: Sat, 17 Oct 2026 00:55:06 GMT`, `Cache-Control: max-age=600`.

## 2. Datasets
| dataset_id | granularity | history | cadence |
|---|---|---|---|
| nefin_factors (value-weighted SMB/HML/WML/IML) | daily, 6,367 rows, 852 KB | **2001-01-02 → 2026-09-08**, sorted, no gap > 5 days, no empty cell | stale: page says "Updated Sep 2026"; last obs is 60 days old on 2026-11-07 |
| nefin_factors_equally_weighted | daily, same columns/dates (daily correlation with value-weighted 0.63–0.85 *(from page)*) | same | same |
| *_monthly (both) | monthly, 308 rows | 2001-01 → 2026-08 | complete months only |
Other NEFIN datasets listed (not fetched): Volatility Index IVol-BR (discontinued, ends Apr 2022), Cost of Equity, Dividend Yield (weekly), Illiquidity Index (monthly), Loan Fees (weekly), Portfolios, Short Interest (daily), Spot Rate Curve (discontinued, ends May 2020).

## 3. Layout
- Daily header: `"","Date","Rm_minus_Rf","SMB","HML","WML","IML","Risk_Free"` — first column is an unnamed quoted row counter. Row: `"1",2001-01-02,0.0066006329937922,-0.0044790252105487,0.0309584597314187,0.010002258134053,0.0031994206570906,0.0005785165382947`. Date ISO unquoted; numbers are **fractions** (0.01 = 1%), 16 significant digits; `Risk_Free` is the daily rate (≈0.0005 = ~12.8% a.a.).
- Monthly header: `year,month,Rm_minus_Rf,SMB,HML,WML,IML,Risk_Free` (no counter, no quotes); monthly factor = spread of monthly portfolio returns, not compounded daily *(from page)*.

## 4. Quirks
- ASCII, `,` separator, LF, decimal point. Row counter restarts if rows are inserted — do not use as a key. Factor values are model outputs and may be restated in a re-estimate (whole file replaced) *(not verified)*.
- Staleness: ~2-month lag; treat as slow-moving, S-tier research input.

## 5. Identity fields
None (market-level series); series_id by column name + weighting.

## 6. Ephemerality
Not ephemeral; the full history is re-published each update. Archive the file when ETag changes (850 KB).

## 7. Open questions
- Update cadence (monthly? quarterly?) and licence/citation terms; whether history is restated between releases.

## 8. Parsed (staging, `ingest/nefin.py`, 2026-11-07)
`factor`: wide, one row per (weighting value|equal, frequency D|M, `period_start`): rm_minus_rf, smb, hml, wml, iml, risk_free as exact decimals (fractions per period; exponent notation such as `7.18e-05` occurs and is exact). The row counter is dropped. Whole-file re-sends keep only changed rows (`dedup_staging`). Reparse: 13,350 rows (6,367 x 2 daily + 308 x 2 monthly), 0 quarantined.
