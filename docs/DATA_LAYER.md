# LASTRO data layer: what is available for modelling

Measured on 2026-11-09, after every backfill finished. Counts are rows; dates are the first and last held. This is a
snapshot: `uv run fin status` and the catalog give the live state. Everything is local, from official or public
sources, collected for personal use (ADR-0012).

## 1. How to read it

- **One entry point:** `data/catalog.duckdb`, DuckDB views over Parquet (rebuilt by `fin catalog`). Open it read-only
  from Python (`duckdb.connect("data/catalog.duckdb", read_only=True)`), or from R, Julia or the DuckDB CLI.
- **Staging-only tables:** a few large or specialised sets have no view and are read straight from Parquet:
  `read_parquet('data/staging/<source>/<dataset>/**/*.parquet', hive_partitioning=false)`. They are listed under
  "staging" below.
- **Ready-made panels:** `fin export panel` writes `data/exports/panel/` (§10), with a column dictionary in its README.
- **Conventions on every row:**
  - **Provenance:** `raw_sha256` and `raw_locator` point to the exact bytes and place in the original file.
  - **Units:** every numeric column states its unit (BRL, shares, %, ratio); money is `Decimal` in the store.
  - **Time:**
    - *valid time* is the date a value refers to (`trade_date`, `reference_date`, `vt_*`);
    - *knowledge time* is when it became known (`kt_published_at`, `kt_first_seen_at`, `received_on`,
      `delivered_on`).
  - **Point in time:** filter by knowledge time ≤ your decision date to get the information set as of that date
    (restated filings, revised macro series).
- **Identity:** `instrument_id` (stocks, units, FIIs, ETFs, BDRs) and `issuer_id` (companies) are our own surrogate
  keys. Tickers, ISINs and CNPJs are time-ranged attributes. A line keeps its id through ticker changes; dead and
  delisted lines are kept, so universes are survivorship-free.
- **Calendar:** ANBIMA/B3 business days 1986→ (ADR-0024).

## 2. Equities and listed instruments (B3)

| View | Grain | Coverage | Rows | Notes |
|---|---|---|---|---|
| `price_daily` | instrument × session × market segment (standard lot, odd lot) | 1986-01-02 → 2026-11-06 | 7.34 M | B3 COTAHIST: OHLC, average, best bid/ask, trades, quantity, volume, quote factor. Raw prices as traded (BRL; pre-1994 currencies converted by `brl_num/brl_den`). 8,469 instruments. |
| `price_adjusted` | instrument × session | 1986 → 2026-11-06 | 4.84 M | `close`, `close_split_adjusted`, `close_adjusted` (splits plus cash, total-return basis). Derived on read from the events below. |
| `corporate_event` | event | 1986 → 2026 | 53,030 | Splits, reverse splits, bonuses, quote-basis changes, spin-offs, dividends, JCP, rights, amortisations. `status` says whether it is applied; `sources` and `price_check` give the evidence (ADR-0016, ADR-0035). |
| `adjustment_factor` | instrument × ex-date | 1986 → 2026 | 46,475 | `split_factor`, `cash_factor`, the multiplicative factors behind `price_adjusted`. |
| `instrument`, `instrument_identifier`, `instrument_link` | instrument; its tickers/ISINs over time; successor links | 1986 → | 8,469 / 23,426 / 260 | Identity through renames, migrations and mergers. |
| `price_report_close` | ticker × session | 2018-01-02 → 2026-11-09 | 18.4 M | B3 Price Report closes, including the fixed-income ETFs COTAHIST omits. |
| `index_composition` | bulletin × index × asset | 2022-03-21 → 2026-11-05 | 2.93 M | 31 B3 indices: theoretical quantity, weight, quadrimester, preview portfolios (ADR-0034). |
| `index_total` | bulletin × index | 2022-03-21 → | 34,920 | B3's printed total and divisor, and whether the rows add up to it. |
| `index_member` | month × index × ticker | 2018-06 → 2026-11 | 155,262 | Point-in-time membership. B3's portfolio from 2022-03 (no month missing); before that, the holdings of the ETF measured to track the index, for Ibovespa, SMLL, IBrX-50, IBrX-100, IDIV, ISE, ICO2, IGCT and IMAT (`source`, ADR-0036). |
| `etf_index` | ETF × index | | 26 | Which ETF tracks which index, measured on holdings (Jaccard 0.94–1.0). |
| `lending_open` | session × asset × market | 2022-03-18 → 2026-11-05 | 2.10 M | Stock-lending open balances (quantity, average price, BRL), the short-interest series. Per market (electronic D+0/D+1, registered) plus total; per asset only until mid-2024. |
| `lending_trade` | session × asset × market | 2023-07-10 → 2026-11-05 | 1.91 M | Registered lending contracts: count, quantity, value, lender and borrower rates (min/weighted average/max, % a year). |
| `intraday_bar` | ticker × 5 min | 2026-09-14 → | 587 k | Yahoo 5-minute bars (tier U, archived going forward only). |

**Staging:**
- `b3_pesquisapregao/price_report`, 65.3 M rows, 2018-01-02 →: the full Price Report for every listed instrument (stocks, options, futures, ETFs). It has settlements, open interest, trade counts, quantities and best bid/ask, with option and future fields.
- `pyield_data/future_daily`, 519 k rows, 2018 →: daily DI1/DOL/IND futures with settlement and open interest.

## 3. Companies and fundamentals (CVM)

| View | Grain | Coverage | Rows | Notes |
|---|---|---|---|---|
| `fundamental_fact` | filing version × statement line | periods 2010-12 → 2026-09 | 79.3 M | Every DFP/ITR line (BPA, BPP, DRE, DFC, DMPL, DVA; individual and consolidated) of 1,230 companies and 42,229 filings. Every **version**: open data's latest plus all superseded versions recovered from RAD (ADR-0027). `received_on` is the knowledge date: point in time across restatements verified on 506/506 restated filings. |
| `fundamental_metric` | filing version × metric | 2010-12 → 2026-09 | 1.34 M | 17 standardised metrics: revenue, gross_profit, ebit, pretax_income, net_income, net_income_controlling, total_assets, current_assets/liabilities, noncurrent_liabilities, equity, equity_controlling, noncontrolling_interest, cash, cash_from_operations/investing/financing. |
| `share_count` | filing version | 2010 → 2026 | 28,913 | Shares by class, treasury shares, anchored to B3 totals. |
| `issuer`, `issuer_instrument` | company; company ↔ share lines | | 3,976 / 4,175 | CNPJ, CVM code, sector, registration dates; how each share line is tied to its issuer. 1,177 of 1,204 lines trading since 2010 are linked (ADR-0018). |
| `insider_movement` | company × month × role group × movement | 2018-12 → 2026-09 | 420 k | CVM VLMO: holdings and trades of controllers, board, officers and others, with delivery date and version. |
| `valuation()`, `universe()` | table functions | | | Market cap, P/E, P/B by date, as known then; the tradable universe at a date. |

**Staging:**
- `cvm_fre/*`: capital history, treasury shares and documents, 2010 →.
- `cvm_fca/*`: registration data and securities, with trading codes by year.
- `cvm_ipe/document`: 749 k IPE filings 2003 →, covering material facts, notices and meetings, with subject and link.
- `cvm_ipe_docs/ipe_ratio`: stock-event ratios read from 367 filings.

## 4. Funds

| View / table | Grain | Coverage | Rows | Notes |
|---|---|---|---|---|
| staging `cvm_fi_inf_diario/daily` | fund × day | 2000-01-03 → 2026-11-06 | 82.0 M | Daily NAV of every Brazilian fund (CVM): quota value, net assets, flows, holders. |
| staging `cvm_fi_cda/position` / `net_assets` | fund × month × holding | 2005-01 → 2026-10 | 100.9 M / 3.9 M | Monthly portfolio composition of every fund. |
| `etf_nav`, `etf_daily` | ETF × day | 2004-07 → 2026-11-06 | 201 k / 245 k | ETF daily reports: quota, net assets, flows. `etf_daily` has every version, `etf_nav` the latest per date. |
| `etf_link` | ETF ↔ listed quota | | 224 | Verified against market price (median ratio within 10 %, ADR-0029). |
| `etf_position` | ETF × month × holding | 2018-06 → 2026-10 | 453 k | ETF portfolios (Fundos.NET CDA), with tickers. |
| `fii_distribution` | FII payout | 2016-11 → | 40,787 | Real-estate fund distributions with delivery minute. |
| staging `cvm_fii/*` | FII × month/quarter | 2016 → 2026 | up to 253 k | FII monthly balance and holders, quarterly assets and properties (area, vacancy, delinquency), annual reports; Fiagro from 2025. |

## 5. Fixed income

| View / table | Grain | Coverage | Rows | Notes |
|---|---|---|---|---|
| `tesouro_bond`, `tesouro_price_daily` | bond; bond × day | 2004-12-31 → 2026-11-06 | 150 / 178 k | Tesouro Direto buy/sell rates and PU for every title (Prefixado, Selic, IPCA+, IGPM+, Renda+, Educa+). |
| staging `pyield_data/bond_rate` | bond × day | 2020-01-02 → | 78,825 | ANBIMA indicative rates of federal bonds (mirror, equal to ANBIMA on overlap). |
| `series_observation` `anbima_ima:*` | index × day | 2001-12 → 2026-11 | 653 k | 178 IMA index series (IMA-B, IRF-M, IMA-S and subindices). |
| staging `b3_pesquisapregao/swap_rate` | curve × day × vertex | 2001-01-02 → 2026-11-06 | 111 M | Every B3 reference curve (TaxaSwap: PRE/DI, IPCA coupon, dollar coupon, etc.). |
| staging `susep_ettj/vertex` | month × vertex | 2015-12 → 2026-10 | 9,282 | ANBIMA ETTJ term structure at month ends (SUSEP copy): nominal, real, implied inflation. Daily from 2026-10-29 in `anbima_ettj`. |
| `debenture`, `debenture_terms`, `debenture_pu`, `debenture_secondary_price` | debenture; × day | 1994 → 2026 | 10 k / 14 k / 7.5 M / 715 k | SND terms, accrued PU, secondary trades (ADR-0028). |
| staging `b3_fixed_income/fi_trade` | trade | 2023-03-13 → | 18.5 M | B3 OTC fixed-income trades (CRI, CRA, debentures, bank paper): price, rate, volume. |

## 6. Rates, FX, macro and context: `series_observation` (1.75 M observations, 1,528 series)

| Source prefix | Series | Coverage | What |
|---|---|---|---|
| `bcb_sgs` | 68 | 1944 → 2026-11-09 | Selic, CDI, TR, savings, IPCA and cores, IGP-M/DI, INPC, IBC-Br, credit, delinquency, spreads, balance of payments, public debt, unemployment |
| `bcb_ptax` | 20 | 1984-12 → | PTAX buy/sell for USD, EUR, GBP, JPY, CHF, CAD, AUD, DKK, NOK, SEK |
| `ibge_sidra` | 934 | 1979 → 2026Q2 | IPCA by item, GDP, industrial production, retail, services, employment |
| `ipeadata` | 16 | 1939 → | including Ibovespa history |
| `fred` | 26 | 1919 → | Fed funds, SOFR, Treasuries, breakevens, TIPS, CPI/PCE, payrolls, unemployment, GDP, industrial production, HY and EM spreads, dollar indices, WTI/Brent, S&P 500, Nasdaq. ALFRED vintages for 7 revisable series (`version`, `kt_published_at`). |
| `us_treasury`, `nyfed`, `ecb`, `bis`, `imf`, `oecd` | 19 / 17 / 7 / 12 / 10 / 4 | 1946 → | US yield curve, NY Fed reference rates, ECB, policy rates, global macro |
| `cboe` | 14 | 1990 → | VIX and other volatility indices |
| `worldbank_cmo`, `cepea`, `anp`, `eia` | 71 / 16 / 78 / 2 | 1960 → | Commodity prices (World Bank Pink Sheet), Brazilian agricultural prices (CEPEA), fuel prices (ANP), oil (EIA) |
| `tesouro_vna` | 3 | 2000 → | VNA of NTN-B, NTN-C, LFT |

Also:
- `focus_expectation`, 3.6 M rows, 2000 → 2026-10: the BCB Focus survey (mean, median, dispersion and respondents by indicator and horizon).
- `copom_decision`: 290 Copom meetings.
- `cftc_position`: CFTC Commitments of Traders, 5.2 M rows, 2010 →.
- NEFIN Brazilian factors (staging `nefin`).
- `us_daily_price`: Tiingo daily prices of 17 US ETFs and Brazilian ADRs (SPY, IVV, QQQ, VT, ACWI, EEM, EWZ, TLT, IEF, SHY, GLD, VNQ, PBR, VALE, ITUB, BBD, ABEV), 1993 →.
- `crypto_daily`: Binance klines for BTC, ETH, SOL against BRL/USDT, 2017 →.

## 7. Quality and evidence

- `dq_finding` holds 2,362 findings from 16 named checks; each is decided by rule or by review, nothing silently
  dropped. Quarantined rows are kept apart in `data/quarantine/`.
- **Exit criteria pass** (`scripts/check_exit_criteria.py`, docs/evaluation/2026-11-08-exit-criteria.md):
  - B3 calendar against sessions;
  - Selic and CDI compounding, 323/323 months;
  - balance identity on 29,399 of 29,408 filings (the 9 breaks are the companies' own);
  - point in time across restatements, 506/506;
  - fund look-through at 0.0003 %.
- **Golden checks:** 9 corporate-event cases exact; a reference portfolio reproduced within 0.2 pp.

## 8. Known limits (measured, not missing by accident)

| Item | Limit | Why |
|---|---|---|
| Company fundamentals | from 2010 (statements from the 2011 filings) | CVM's open data and RAD start there |
| Index membership | official 2022-03 →; 9 indices back to 2018 via ETF holdings | B3 publishes compositions only in the daily bulletin, served from 2022-03 |
| Stock lending | balances 2022-03 →, contracts 2023-07 → | Same bulletin; the 2022–23 layout prints balances only |
| Futures settlements | 2018 → | No free source before (COTAHIST has none; B3 curves cover rates from 2001) |
| ANBIMA bond rates | 2020 → (Tesouro Direto prices from 2004 as a proxy) | ANBIMA serves only recent days; the 2020 → mirror is public |
| ETTJ | month ends 2015-12 →, daily from 2026-10-29 | Same |
| Intraday | from 2026-09 only | Yahoo serves recent bars only |
| Lost or unpublished days | 14 bulletin days in 2022; one RAD document; 21 of 7,473 filing versions unparsed | The source's own (HTTP 500, broken metadata); recorded in the source notes |

## 9. Points that matter for modelling

- **Survivorship:** delisted and dead lines are kept with their full history. `universe()` and `index_member` give
  who was investable at each date.
- **Look-ahead:** fundamentals carry `received_on`. Use the version received on or before the decision date; the
  panel already does this. Macro revisions: FRED vintages and series `version`.
- **Adjusted prices:**
  - use `price_adjusted.close_adjusted` for total-return work and `close_split_adjusted` for price-only work;
  - raw `price_daily` is as traded;
  - events are evidence-graded, and a few unresolvable ones stay unapplied with a `dq_finding`.
- **Extreme months:**
  - the panel flags 57 month-returns beyond 4× up or down (`ret_suspect`). Each was checked: real liquid
    crashes or rallies (Americanas 2023, PDG, Gol, Azul, the TXRX3 2020 mania) or prints on lines with fewer
    than 200 trades that month;
  - filter or winsorise them as the model needs;
  - illiquidity in general shows in `sessions`, `days_stale` and `avg_daily_volume_brl`.
- **Frequencies:** daily for prices, rates, FX, curves, fund NAVs, lending and bulletins; monthly for fund
  portfolios, index membership, insider trades, most macro; quarterly for fundamentals; weekly for CFTC.
- **Currency and units:** BRL throughout except where a column says USD or another currency (FRED, US ETFs, crypto
  against USDT).

## 10. Ready-made panels (`data/exports/panel/`)

- `equity_monthly.parquet`: 85,932 rows, 1,160 share lines, 2010-01 → 2026-11.
  - Per line and month: ticker, issuer, sector, sessions, staleness, volume, close.
  - Returns: total and price returns, `ret_suspect`.
  - Signals: 12-1 momentum, 12-month volatility, dividend yield.
  - Fundamentals as known then: market cap, P/E, P/B, trailing earnings, book value. They are filled on 66,196
    rows (from 2011).
  - The characteristics of month t use data up to month end t, and returns are realised in t. To predict, use the
    characteristics of t-1.
- `macro_monthly.parquet`: 203 months. CDI, Selic (month and target), IPCA, IGP-M, IBC-Br, Ibovespa, USD/BRL PTAX,
  Fed funds, US 10-year.
- The panels are built from the catalog in a few seconds (`fin export panel`). A daily or weekly panel, or other
  columns, can be added the same way from the views above.

## 11. Keeping it current

The Windows task "LASTRO fin ingest daily" runs every day at 22:30 and at logon (RUNBOOK). It archives the
today-only sources and appends new days everywhere; a missed day is caught up while the source still serves it.
