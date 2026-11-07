# PLAN.md — Personal Investment Data & Analysis System (Brazil)

> **Audience:** Claude Code, acting as implementing engineer.
> **Owner:** Levi (architect and sole user).
> **Status:** Foundational plan. It supersedes any earlier code or design from the owner's previous attempt at this project.
> **Reading order:** sections 1–3 for context. **Section 4 (Data layer) is the core of this document and of the project. Read it in full before writing any code.**

---

## 0. How to use this document

1. **Treat this plan as the source of intent, not of facts about the outside world.**
   - Every external data source, endpoint, file layout and field name below is a **hypothesis to verify**. Reconnaissance (§4.13) comes before any connector code.
   - Where this plan and reality disagree, reality wins. Record the discrepancy in `docs/DECISIONS.md` and the source's recon note.
2. **Keep the long-lived instructions in `CLAUDE.md`.** Create `CLAUDE.md` at the repo root and hold it to:
   - the invariants of §4.1;
   - the working agreement of §11;
   - the repository conventions of §9.

   Keep it short. This PLAN.md stays the long-form reference.
3. **Order the work by dependency, not by calendar.** §10 defines stages and exit criteria. A stage is done when its exit criteria pass, not when code exists.
4. **Ask when blocked on a decision that belongs to the owner.** §12 lists the questions already open. Otherwise choose the conventional option, record it in `docs/DECISIONS.md`, and continue.

---

## 1. Purpose, scope and non-goals

### 1.1 Purpose

The system is a local, owner-controlled platform that:

1. **Acquires** rich financial data on every asset class reachable by a Brazilian tax resident, keeps it, and makes it trustworthy.
2. **Models** what the owner holds, through time, across every corporate action and instrument change.
3. **Values** every holding: market price where one exists, model price where none exists.
4. **Analyzes** return, risk, exposures and scenarios using contemporary statistical practice.
5. **Exports** compact, provenance-rich dossiers that the owner hands to an external LLM for discussion and adjudication.

### 1.2 Asset scope (all of it)

- **Exchange-listed:** shares (ON, PN, units), BDRs, ETFs (equity, fixed-income, crypto), FIIs, Fiagros, FI-Infra, listed options, futures (DI1, DOL/WDO, IND/WIN and others relevant to curves and hedging), subscription rights and receipts.
- **Funds:** all CVM-registered funds and classes under Resolução CVM 175 (FIA, multimercado, renda fixa, cambial, FIDC, FIP where data exists), pension-plan FIEs (PGBL/VGBL underlying).
- **Government bonds:** Tesouro Direto (LTN, NTN-F, LFT, NTN-B, NTN-B Principal, Renda+, Educa+), plus secondary-market reference prices.
- **Bank and private credit:** CDB, RDB, LCI, LCA, LCD, LIG, LF, debentures (including incentivadas, Lei 12.431), CRI, CRA, COE.
- **Cash-like:** poupança, CDI-indexed accounts.
- **Crypto:** spot holdings at Brazilian and global exchanges; B3-listed crypto ETFs.
- **Offshore:** foreign brokerage holdings (taxed under Lei 14.754/2023), converted at PTAX.
- **Context data** (not held, but needed for analysis): macro series, curves, indices, factors, FX, commodities, survey expectations.

### 1.3 Non-goals

- **No "solve the market" modeling.**
  - The system does not try to forecast expected returns of assets for alpha.
  - Forecasting is limited to quantities that are forecastable and useful: volatility, liquidity, flows, payouts, scenario paths.
- **No dependence on SaaS or proprietary platforms for core function.**
  - Paid or unofficial sources may serve as cross-checks or fallbacks.
  - They are never the sole source of truth when a primary source exists.
- **No embedded chatbot or agent.**
  - LLM adjudication happens outside the system.
  - LLMs may be used *inside* the data layer only as extraction tools (§4.7.4), under verification.
- **No automated trading or order placement.**
- **No GUI requirement** in early stages. A UI, if built later, follows the owner's UI preferences: pt-BR labels, data-driven selectors, soft surfaces.

---

## 2. Operating constraints

| Constraint | Value |
|---|---|
| Host | Owner's laptop: Windows, i7-13700H, 32 GB DDR5, RTX 4050 (6 GB VRAM). All code must run natively on Windows; avoid POSIX-only assumptions (paths, shell scripts, `fork`). WSL is optional and must not be required. |
| Language | Python ≥ 3.12, managed with `uv`. |
| Storage / compute | Parquet files + DuckDB (in-process) as the analytical engine; Polars where dataframe code is clearer. No database server. |
| Network | Ordinary residential internet; sources must be fetched politely (§4.12). |
| GPU | Used only for analytics (time-series foundation models, embeddings, optional small local LLMs via LM Studio). The data layer must not need the GPU. |
| LLM access | The owner has an OpenAI-compatible endpoint (local LM Studio and/or a proxy to frontier models). Any LLM use goes through one configurable client interface; no vendor SDK lock-in. Embeddings run locally. |
| Scale | Tens of GB on disk at full history; must stay fully local. |
| Cost | Free primary sources first. Paid sources only if the owner approves (§12). |

---

## 3. Architecture overview

Six layers, built strictly in dependency order. Each layer reads only from layers above it.

```
L0  Reference & calendar     ANBIMA/B3 business-day calendars, currencies, units, source registry
L1  Raw archive              immutable, content-addressed copies of everything fetched
L2  Normalized (staging)     typed, schema-validated tables per source, still source-shaped
L3  Core (canonical model)   source-agnostic entities: issuers, instruments, identifiers, events,
                             prices, quotas, rates, curves, terms, filings, fundamentals, holdings
L4  Derived                  adjustment factors, total-return indices, curves fitted, valuations,
                             positions, P&L, exposures, risk
L5  Export                   dossiers for the external LLM adjudicator
```

**The ledger** (the owner's transactions, positions, basis and taxes) is a core-layer domain fed by the owner's own documents and reconciled against custody (§5).

**The valuation engine** (§6) and **analytics** (§7) live in L4.

**The design rule that governs everything: store facts immutably; derive everything else on read or in rebuildable derived tables.** Never store a number that some other stored number determines unless it is a cache marked as such and rebuildable from scratch.

---

## 4. DATA LAYER — the critical layer

> **This is where the project lives or dies.** The owner's previous attempt failed here. The causes were data availability, data quality, instrument identity through time, and price adjustment.
>
> Expect this layer to be the large majority of the codebase, the tests and the effort. Depth here is the requirement, not a risk.
>
> Do not move to valuation or analytics until the exit criteria of the data stages in §10 pass.

### 4.1 Invariants (non-negotiable; copy into CLAUDE.md)

1. **Raw is immutable.**
   - Every fetched payload is stored byte-for-byte in L1, content-addressed (SHA-256), with a manifest entry. It is never edited or deleted.
   - Normalization bugs are fixed by re-deriving from raw, never by patching data.
2. **Every row carries provenance.**
   - Every L2/L3 row references the raw object it came from (`raw_sha256`, plus a locator: file member, line number, JSON path, PDF page) and the `ingest_run_id`.
   - A number without provenance is a defect.
3. **Bitemporality.** Every fact in L3 carries two clocks:
   - **valid time**: when it is true in the world (`valid_from`/`valid_to`, or `as_of_date`, ex-date, reference period);
   - **knowledge time**: when it became knowable or known (`published_at` where the source states it; `first_seen_at` = when our archive first contained it).

   Any query must be answerable "as known at instant K". Restatements create new versions; they never overwrite.
4. **Identity is ours.**
   - Instruments and issuers have internal surrogate keys that never change.
   - Tickers, ISINs, CNPJs, CVM codes, fund-class codes and exchange codes are time-ranged attributes of those keys, never keys themselves.
5. **Point-in-time universes.** The set of instruments that existed or traded on date D must be reconstructible, including delisted, merged and dead instruments. Survivorship bias is a defect.
6. **Derive, don't store adjusted data.**
   - Raw prices and raw events are stored.
   - Adjusted prices, total-return indices and positions are derived and rebuildable.
7. **Reconcile, don't trust.**
   - Every important fact class has at least one independent cross-check (§4.11).
   - Disagreements become explicit `dq_finding` records with a resolution status. They are never resolved silently by "picking a winner" in code.
8. **Explicit units and conventions.**
   - Every numeric column states its unit, currency, scale (e.g., CVM "MIL"), quote basis (per share vs per lot: COTAHIST `FATCOT`) and day-count/compounding convention where relevant.
   - Implicit units are defects.
9. **Canonical calendar.** All business-day arithmetic uses the versioned ANBIMA national calendar (and the B3 trading calendar where they differ). Never use a generic library's holiday set.
10. **Idempotency and replay.**
    - Every pipeline step is idempotent on its inputs.
    - The entire L2–L4 state must be rebuildable from L1 plus code, and a full rebuild is a supported, tested operation.
11. **Fail loudly, quarantine, never drop.**
    - Rows that fail validation go to quarantine tables with the reason.
    - Silent row loss is the worst class of bug.
    - Every ingest reports row counts in/out/quarantined.
12. **Completeness is measured.**
    - For each source and date range, the system knows what *should* exist (expected files and dates, expected instruments) and reports coverage gaps.
13. **Archive the ephemeral.**
    - Some sources only publish "today" (daily instrument registries, intraday files, rolling-window datasets).
    - These are fetched on schedule and archived from day one; lost days are unrecoverable.
    - The daily snapshot job is a first-class component, not an afterthought.

### 4.2 Storage layout and zones

```
data/
  raw/                       L1 — content-addressed: raw/<sha256[0:2]>/<sha256>.<ext>
  manifest/                  L1 index: one row per fetched object (Parquet + DuckDB view)
  staging/<source>/<dataset>/   L2 — Parquet, partitioned by natural period (year or date)
  core/<domain>/<table>/     L3 — Parquet (or DuckLake tables; see decision below)
  derived/<domain>/<table>/  L4 — rebuildable
  quarantine/<source>/<dataset>/
  exports/                   L5 dossiers
catalog.duckdb               views over all zones; macros; no data that cannot be rebuilt
```

**Manifest row:**
- `raw_sha256`, `source_id`, `dataset_id`;
- `request` (URL or method plus parameters, credentials redacted);
- `fetched_at` (UTC), `http_status`, `content_type`, `bytes`;
- `source_reference_date` (the business date the payload refers to, if any);
- `ingest_run_id`, `connector_version`, `notes`.

**Table format decision** (record in DECISIONS.md after a spike): plain partitioned Parquet with DuckDB views, versus DuckLake (snapshot/time-travel semantics). Default: plain Parquet + explicit bitemporal columns, because the bitemporal model is explicit in the schema anyway.

**Partitioning:**
- Daily market data by year; filings by reference year.
- Avoid over-partitioning: no partitions under ~50 MB unless required for incremental writes.

**Compression:** zstd. **Row groups:** sized for DuckDB scans (~100k–1M rows).

### 4.3 Canonical model (L3)

This section lists the minimum entity set. Column lists are indicative; refine during design, but keep the bitemporal and provenance columns everywhere. Notation:
- `vt_*` = valid-time columns;
- `kt_*` = knowledge-time columns (`kt_published_at`, `kt_first_seen_at`);
- every table also has `raw_sha256`, `raw_locator`, `ingest_run_id`, `record_version`, `superseded_by` (where versioned).

#### 4.3.1 Reference

- **`calendar_day`**: `date`, `is_anbima_business_day`, `is_b3_trading_day`, `du_index` (cumulative business-day ordinal), `calendar_version`.
- **`source_registry`**: `source_id`, name, owner institution, access method, license/terms notes, `official` (bool), reliability tier (`primary` / `secondary` / `unofficial`), recon note path.
- **`unit`**, **`currency`**, **`indexer`** (CDI, SELIC, IPCA, IGP-M, TR, PTAX-USD, prefixado), **`day_count_convention`** (`BUS/252`, `ACT/365`, `30/360`…).

#### 4.3.2 Parties and identity

- **`issuer`**: `issuer_id` (surrogate), `kind` (company, government, bank, fund-manager, SPV/securitizer, foreign).
- **`issuer_identifier`** (time-ranged): `issuer_id`, `scheme` (CNPJ, CVM_CODE, B3_ISSUER_CODE (4-letter), LEI, foreign IDs), `value`, `vt_from`, `vt_to`, confidence, source.
- **`issuer_name`** (time-ranged): legal and trading names. Renames are frequent.
- **`instrument`**: `instrument_id` (surrogate), `asset_class`, `subtype`, `issuer_id`, `currency`, `listing_venue` (B3 listed / B3 balcão / Tesouro Direto / bank / foreign / crypto exchange), `lifecycle_status`.
- **`instrument_identifier`** (time-ranged; SCD type 2): `instrument_id`, `scheme` (TICKER, ISIN, CVM_FUND_CNPJ, CVM_CLASS_CODE, SUBCLASS, TESOURO_CODE, SELIC_CODE, CETIP/B3_BALCAO_CODE, ANBIMA_CODE, EXCHANGE_SYMBOL), `value`, `vt_from`, `vt_to`, source, confidence, `resolution_method`.
  - Must support ticker reuse by different instruments in non-overlapping periods.
  - Must support multiple simultaneous identifiers under one scheme where reality has them (e.g., odd-lot ticker `XXXX3F`, modeled as a market segment of the same instrument rather than a separate instrument; record the decision).
- **`instrument_attribute`** (time-ranged key/value for slowly changing attributes): share class, governance segment (Novo Mercado, N1, N2), lot size, quote factor, tick size, index membership flags. Key/value only where a typed table would be absurd.
- **`instrument_relation`** (time-ranged): unit ↔ components, BDR ↔ underlying foreign share, ETF ↔ tracked index, option/future ↔ underlying, subscription right ↔ parent share, fund subclass ↔ class ↔ fund.

#### 4.3.3 Corporate events (the lineage graph)

- **`corporate_event`**: `event_id`, `issuer_id`, `event_type` (enum below), `announced_at` (knowledge time; from CVM IPE/B3), `approval_date`, `data_com`, `ex_date`, `record_date`, `payment_date` (nullable; may be announced later, so versioned), `status` (announced, confirmed, amended, cancelled), source references, `extraction_method` (structured / LLM-extracted / manual), `verification_status`.
- **`event_leg`** (edges of the graph): `event_id`, `from_instrument_id`, `to_instrument_id` (nullable for cash), `leg_kind` (`shares`, `cash`, `right`, `fraction_cash`, `basis_transfer`), `ratio_num` / `ratio_den` (exact rationals, never floats), `cash_per_share` (exact decimal, currency), `gross_or_net`, `tax_treatment_code`, `cost_basis_rule` (e.g., custo atribuído per share; spin-off basis percentage).
- **Event types (minimum):**
  - **Cash payouts:**
    - `DIVIDEND`;
    - `JCP` (gross amount; withholding derived from the tax engine);
    - `RENDIMENTO` (FII/Fiagro distribution);
    - `AMORTIZATION` (FII/debenture/CRI principal return);
    - `RESTITUICAO_CAPITAL` (capital return).
  - **Share-count changes:**
    - `SPLIT` (desdobramento);
    - `REVERSE_SPLIT` (grupamento);
    - `BONUS` (bonificação, with custo atribuído).
  - **Rights:**
    - `SUBSCRIPTION_RIGHT_GRANT`;
    - `SUBSCRIPTION_EXERCISE_WINDOW`;
    - `SUBSCRIPTION_RECEIPT_CONVERSION`.
  - **Restructurings:**
    - `MERGER` (incorporação / incorporação de ações);
    - `SPIN_OFF` (cisão total/parcial);
    - `TICKER_CHANGE`, `ISIN_CHANGE`, `NAME_CHANGE` (identity-only events);
    - `UNIT_CONVERSION` (units ↔ components);
    - `TENDER_OFFER` (OPA);
    - `DELISTING`;
    - `CONVERSION` (class conversion PN↔ON).
  - **Fractions:** `FRACTION_AUCTION` (leilão de frações).
  - **Fund events:**
    - `FUND_CLASS_RESTRUCTURE` (CVM 175 adaptation);
    - `FUND_MERGER`, `FUND_SPLIT`;
    - `COME_COTAS` (generated by the tax engine, not sourced).
  - **Bond/credit events:**
    - `BOND_COUPON`, `BOND_MATURITY`, `EARLY_REDEMPTION` (resgate antecipado);
    - `DEFAULT`, `RESTRUCTURING` (credit events).

**Invariants:**
- Graph legs conserve value up to the stated cash leg.
- Ratios are exact rationals.
- Every share-count leg has a basis rule.
- Event amendments create new versions with `kt_*` timestamps.

#### 4.3.4 Market observations

- **`price_daily`** (exchange-traded, raw, unadjusted): `instrument_id`, `trade_date`, `market_segment` (lote padrão, fracionário, termo, after-market if relevant), `open`, `high`, `low`, `close`, `avg`, `best_bid`, `best_ask`, `n_trades`, `qty`, `volume_brl`, `quote_factor`, `distribution_number` (COTAHIST `DISMES`), `source_id`.
  - Prices are stored as exact decimals in BRL per **one unit of the instrument** after applying the quote factor. Keep the original quoted value and factor as well.
- **`price_intraday`** (optional, archive-forward): trades or bars where B3 publishes them.
- **`settlement_price`** (futures and options): `instrument_id`, `date`, `settlement_price`, `open_interest`, `rate_implied` (for DI1).
- **`fund_quota_daily`**: `fund_class_id`, `date`, `quota_value`, `nav` (patrimônio líquido), `inflows`, `outflows`, `n_holders`, `total_assets`. These are net of fees by construction; document it.
- **`tesouro_price_daily`**: `instrument_id`, `date`, `buy_rate`, `sell_rate`, `buy_pu`, `sell_pu`, `base_pu`; plus any secondary-market reference (ANBIMA indicative rate/PU).
- **`credit_reference_daily`** (debentures, CRI, CRA, LF where available): ANBIMA indicative rate, PU, duration, spread, intervals; plus B3 balcão trades where available.
- **`series_observation`** (macro, rates, indices, factors, FX, survey expectations — one long table): `series_id`, `vt_reference` (date or period; monthly series store the period, not a fake date), `value`, `unit`, `kt_published_at`, `vintage` (for revised series), source.
- **`series_definition`**: `series_id`, source code (e.g., SGS code), frequency, unit, seasonal adjustment, transformation, description (pt-BR and en).
- **`curve_snapshot`**: `curve_id` (pré-DI, IPCA real, IGP-M, cupom cambial…), `date`, `representation` (`params` / `vertices`), parameters (e.g., Svensson β0–β3, λ1–λ2) and/or vertices (`du`, `rate`), source, `fit_quality`.
- **`index_composition`**: `index_id`, `instrument_id`, `vt_from`, `vt_to`, theoretical quantity, weight at publication (B3 quarterly carteiras teóricas and previews). Needed for point-in-time benchmark universes.
- **`securities_lending`**, **`investor_participation`**, **`short_interest`**: if B3 publishes them freely (to verify), as context for liquidity and positioning.

#### 4.3.5 Contract terms and cash flows (non-traded valuation inputs)

- **`instrument_terms`**: issue date, maturity, face value, indexer, spread/percent, coupon frequency and rate, amortization schedule, call/put/early-redemption clauses, grace periods, liquidity (daily vs at maturity), FGC eligibility, tax regime code (exempt LCI/LCA/incentivada vs regressive table), day-count convention, truncation/rounding rule (CETIP/B3 TDI rules).
- **`cashflow_schedule`** (derived for indexed instruments, stored for fixed schedules): `instrument_id`, `event_date`, `kind` (interest, amortization, principal), `amount` or `formula_ref`.
- Sources:
  - debentures: SND/B3 issue documents (escritura), ANBIMA characteristics;
  - Tesouro: official title rules;
  - bank paper: the owner's own contracts and broker statements.

#### 4.3.6 Filings, fundamentals and documents

- **`filing`**: `filing_id`, `issuer_id`, `form` (DFP, ITR, FRE, FCA, IPE categories: Fato Relevante, Aviso aos Acionistas, Comunicado ao Mercado, Ata AGO/AGE, Calendário de eventos…), `reference_period`, `version` (reapresentação count), `delivered_at` (knowledge time), document URL, local raw ref.
- **`fundamental_fact`** (long, XBRL-like): `issuer_id`, `filing_id`, `statement` (BPA, BPP, DRE, DRA, DFC-MD/MI, DVA, DMPL), `consolidation` (consolidated / individual), `account_code` (CVM plano de contas code), `account_label`, `period_start`, `period_end`, `value`, `scale` (UNIDADE/MIL), `currency`, `version`.
  - Point-in-time queries select the latest version with `delivered_at ≤ K`.
- **`fundamental_metric`** (derived L4): standardized items (revenue, EBIT, net income, equity, debt, shares outstanding, dividends paid) mapped from account codes with a documented mapping table per statement layout. It handles financials (banks, insurers) separately, because their layouts differ.
- **`shares_outstanding`** (time-ranged): from FRE/FCA/ITR capital-structure fields and corporate events. Needed for market cap and event validation.
- **`insider_trading`**: if CVM VLMO (valores mobiliários negociados por administradores) is available in open data.
- **`document_text`** and **`document_chunk`**: extracted text of PDFs (Avisos, Fatos Relevantes, escrituras, fund regulations) for search and LLM-assisted extraction; embeddings are stored in L4.

#### 4.3.7 Funds

- **`fund`**, **`fund_class`**, **`fund_subclass`** (CVM 175 hierarchy): registration codes, CNPJs, type, ANBIMA classification, manager, administrator, custodian, benchmark, fees (administration, performance, entry/exit), redemption terms (cotização / liquidação D+N), tax regime (long-term / short-term / equity), `vt_*` for every attribute.
- **`fund_holding`** (from CVM CDA — composição e diversificação das aplicações): `fund_class_id`, `reference_month`, `asset identifier` (resolved to `instrument_id` where possible), `quantity`, `market_value`, `asset_type`. Enables look-through exposure.
- **`fii_report`**: FII/Fiagro monthly, quarterly and annual informes (NAV, units, distributions, vacancy, portfolio composition where present).

### 4.4 Source catalog (to verify in reconnaissance)

Reliability tiers: **P** = primary/official, **S** = secondary reputable, **U** = unofficial/undocumented (fallback and cross-check only).

| Domain | Source | Content | Tier | Notes / pitfalls to verify |
|---|---|---|---|---|
| Listed prices | **B3 COTAHIST** (historical quote files: yearly, monthly, daily) | Daily OHLC, volume, trades, ISIN, `DISMES`, `FATCOT`, market type (spot, odd-lot, options, termo), option strike/expiry | P | Fixed-width layout (official layout PDF); prices in centavos with implied decimals; `FATCOT` 1 vs 1000 in old years; history back to 1986; `TPMERC` codes. |
| Instrument registry | **B3 instrument registry files** (e.g., "InstrumentsConsolidated" / cadastro de instrumentos), published daily | Every registered instrument: ticker, ISIN, type, segment, issuer, options/futures specs | P | Verify current location and access (public vs registration). **Archive daily from day one**; history may not be downloadable later. |
| Corporate events | **B3 listed-companies site backend** (JSON used by the B3 company pages) | Cash dividends, stock events (bonificação, split, grupamento), subscriptions, by issuer | U | Undocumented; parameters encoded; may change. Cross-check against CVM IPE documents. |
| Corporate events / filings | **CVM open data (dados.cvm.gov.br): IPE** | Index of eventual documents (Fato Relevante, Aviso aos Acionistas, Atas) with delivery timestamps and links | P | The knowledge-time feed for events; PDFs require extraction (§4.7.4). |
| Companies | **CVM: cadastro de companhias abertas, FCA, FRE** | Registry (CNPJ, CVM code, status, sector), securities listing (tickers per company), capital structure, shareholder structure | P | FCA "valor mobiliário" fields map CNPJ ↔ tickers over time; FRE capital history helps validate events. |
| Fundamentals | **CVM: DFP and ITR** | Annual and quarterly statements as CSV, with versions | P | Scale MIL vs UNIDADE; consolidated vs individual; reapresentações; different layouts for banks and insurers. |
| Insider trades | **CVM: VLMO** (if published as open data) | Monthly trading by insiders | P | Verify availability. |
| Funds | **CVM: Informe Diário (FI/DOC/INF_DIARIO)** | Daily quota value, NAV, flows, holders, for all funds/classes | P | CVM 175 identity changes (fund vs class vs subclass columns); monthly files; historical archives by year. |
| Fund holdings | **CVM: CDA** | Monthly portfolio composition | P | Multiple block files per asset type; confidential positions may be omitted for a lag period. |
| Fund registry | **CVM: cadastro de fundos / registro de classes** | Fund/class/subclass attributes | P | Schema changed with CVM 175; reconcile old and new cadastro. |
| FII / Fiagro | **CVM: informes FII (mensal/trimestral/anual)** + **B3 FII pages / Fundos.NET** | NAV, distributions, portfolio | P / U | Distribution announcements via Fundos.NET documents. |
| Tesouro Direto | **Tesouro Transparente (dados abertos)** | Daily buy/sell rates and PU per title since 2002; also sales, redemptions and stock datasets | P | CSV with pt-BR decimals and dates. |
| Govt bonds (secondary) | **ANBIMA: títulos públicos secondary market** | Daily indicative rates/PU, intervals | P | Verify what remains free vs moved to the paid ANBIMA Feed. |
| Curves | **B3 reference rates (taxas referenciais / curvas)** | DI × pré, DI × IPCA (cupom), others by business-day vertex | P | Daily; archive daily if history is limited. |
| Curves | **ANBIMA ETTJ** | Daily Svensson parameters and vertices for nominal and real curves, implied inflation | P | Free status to verify. |
| Futures | **B3 settlement prices (ajustes do pregão)** + COTAHIST derivatives | DI1, DOL, IND settlement and open interest | P | DI1 PU ↔ rate conversion (100,000 / (1+r)^(du/252)). |
| Debentures / credit | **ANBIMA debentures, CRI/CRA reference data** | Daily indicative rates/PU, duration, characteristics | P | Free coverage to verify. |
| Debentures terms | **SND (debentures.com.br)** / B3 balcão | Issue characteristics, schedules, events, prices | P / S | Verify current host and access. |
| Inflation projections | **ANBIMA IPCA/IGP-M projections** | Monthly projected inflation used for VNA pro-rata | P | Needed for NTN-B intra-month valuation. |
| VNA | **ANBIMA / Tesouro VNA** | Updated nominal value for NTN-B, NTN-C | P | Cross-check with own computation from IPCA. |
| Macro / rates | **BCB SGS** (série temporal API) | CDI daily, Selic daily/target, TR, poupança, IPCA, IGP-M, FX, credit, monetary aggregates… | P | Request windows are limited per call (verify current limits); vintages are not kept, so store kt timestamps. |
| Expectations | **BCB Focus (Olinda API)** | Market expectations by indicator, horizon, statistic | P | Large; store by survey date (knowledge time is natural). |
| FX | **BCB PTAX (Olinda)** | Official FX rates, intraday bulletins | P | PTAX is the tax reference rate. |
| Prices / national accounts | **IBGE SIDRA API** | IPCA (with subitems), IPCA-15, PNAD, GDP | P | Monthly references; revisions. |
| Brazilian factors | **NEFIN (FEA-USP)** | Daily Brazilian risk factors (market, SMB, HML, WML, IML) and risk-free | S | Verify continuity and update cadence. |
| Global context | **FRED** (optional) | US rates, global indices, commodities | P (foreign) | Context only. |
| Crypto | **Exchange public APIs** (e.g., Mercado Bitcoin, Binance) | OHLC, trades | S | Rate limits; symbol identity per exchange. |
| Cross-check | **Yahoo Finance chart endpoint** | Adjusted prices, dividends, splits for .SA tickers | U | Unofficial; merges JCP and dividends; cross-check only. |
| Cross-check | **brapi.dev** (optional, owner approval) | Prices, dividends, fundamentals | S | Free tier; cross-check only. |
| Owner data | **B3 Área do Investidor exports** | Positions, trades, received payouts, events actually applied to the owner | P (for owner) | Manual export files dropped into an inbox folder; ground truth for the ledger. |
| Owner data | **Notas de corretagem (PDF)** | Trades, fees, taxes per trade | P (for owner) | Parse with layout-aware extraction; formats vary by broker (SINACOR standard). |
| Owner data | **Broker/bank statements, CDB/LCI/COE contracts, offshore broker statements, exchange crypto statements** | Terms and flows | P (for owner) | Inbox-driven; LLM-assisted extraction under verification. |

**Rule:** a domain is not "covered" until at least one **P** source is ingested with recon notes, layout documentation, fixtures and tests. **U** sources never feed L3 alone: their facts enter as *candidate* facts requiring corroboration, or as cross-check evidence.

### 4.5 Identity resolution

**Goal:** every observation from every source maps to exactly one `instrument_id` / `issuer_id`, valid through time, with a recorded method and confidence.

**Algorithm (deterministic first, then evidence-based):**

1. **Seed issuers from the CVM cadastro:**
   - CNPJ is the issuer anchor;
   - CVM code and B3 4-letter issuer code are time-ranged attributes;
   - add the government (Tesouro), banks (from BCB/Tesouro/broker data) and securitizers as issuers.
2. **Seed instruments from B3 registries and COTAHIST:**
   - an equity instrument is anchored by (issuer, share class/kind);
   - ISINs and tickers attach as time-ranged identifiers;
   - derive first and last trading dates per (ticker, ISIN) from COTAHIST.
3. **Detect identity transitions:**
   - **ticker changes:** same ISIN, ticker A ends and ticker B begins;
   - **ISIN changes:** same ticker, ISIN changes;
   - **issuer-code changes:** both change around a CVM/B3 rename event.

   Corroborate every transition with a CVM IPE document or B3 notice where possible, and with price continuity (no gap beyond event-explained levels).
4. **Merges and spin-offs** are *not* identity transitions. They create new edges in the event graph (§4.3.3) between distinct instruments.
5. **Ticker reuse:** the same ticker string mapped to different instruments in disjoint periods is allowed and must be tested.
6. **Funds:**
   - pre-CVM 175 funds are anchored by fund CNPJ;
   - after adaptation, classes and subclasses become the investable units.

   Model the transition explicitly (`FUND_CLASS_RESTRUCTURE` event) so quota series remain continuous where economically continuous.
7. **Tesouro titles:** an instrument is the (title type, maturity) pair, e.g., NTN-B 2035-05-15, with the Tesouro code and SELIC code as identifiers.
8. **Bank paper and private credit:** CETIP/B3 balcão codes and ISINs where available; otherwise owner-scoped instruments created from contracts.
9. **Unresolved observations** go to an `identity_review_queue` with candidate matches and evidence. They are never force-matched.
10. **Output:** `identity_resolution_log` (method, evidence refs, confidence, reviewer, timestamp) for every non-trivial link.

### 4.6 Point-in-time universes

Provide a core function/view: `universe(date, asset_class, filters) → set of instrument_id` that uses only facts valid **and** known as of the query (bitemporal), including instruments delisted afterward.

**Test:** the Ibovespa theoretical portfolio at historical dates must be reconstructible from `index_composition`, and every member must resolve to an instrument with price data on that date.

### 4.7 Corporate events: sourcing, extraction, verification

#### 4.7.1 Sourcing priority

1. Structured official data: CVM fields, B3 structured feeds where official.
2. The B3 company-page backend (U).
3. LLM-assisted extraction from CVM IPE documents (Avisos aos Acionistas, Fatos Relevantes, Atas).
4. Cross-check sources (Yahoo, brapi) as corroborating evidence only.

#### 4.7.2 Event lifecycle

```
candidate → corroborated → verified (price/structure checks pass) → applied
         ↘ conflicting (dq_finding) → resolved (with recorded decision)
```

#### 4.7.3 Verification (mandatory for every share-count and cash event)

1. **Price-gap test.** Compute the event-implied adjustment factor and compare it with the realized overnight move from the data-com close to the ex-date open/close, net of the market move (use the Ibovespa or sector return as a control).
   - Flag if the residual exceeds k·σ, where σ is the instrument's recent daily volatility.
   - Choose k with a documented rationale.
2. **Distribution-number test.** A change in COTAHIST `DISMES` must coincide with at least one registered event (ex-date) for that instrument. A registered ex-event without a `DISMES` change must be flagged.
3. **Share-count continuity.** `shares_outstanding` before × ratio ≈ shares after, within tolerance, for splits, bonuses and reverse splits.
4. **Unexplained-gap scan** (reverse direction). Scan all instruments for overnight gaps beyond threshold with no registered event. Each gap becomes either a discovered missing event or a documented market move (with evidence: a Fato Relevante the previous evening, for example).
5. **Owner reconciliation.** For instruments the owner held, events must match the Área do Investidor "eventos/proventos" exports: quantities credited, cash received, fraction-auction cash.

#### 4.7.4 LLM-assisted extraction (inside the data layer, under verification)

- **Use:** extract structured event fields from PDFs or HTML (Avisos, Atas, Fatos Relevantes, escrituras de debêntures, fund regulations) where no structured feed exists or to corroborate one.
- **Interface:** one `LLMExtractor` abstraction over an OpenAI-compatible endpoint (configurable base URL and model; the owner runs LM Studio locally and has a proxy to frontier models).
  - Strict JSON schema output.
  - Temperature 0.
  - Store prompt, model, response and parse result as raw artifacts (content-addressed) for reproducibility.
- **Text acquisition:** PDF text extraction first; OCR fallback only when needed. Keep page references for provenance.
- **Policy:** LLM-extracted facts enter as `candidate` with `extraction_method = llm`. They become `verified` only through §4.7.3 tests or corroboration by a P source. Never let an LLM-extracted number reach L4 unverified.
- **Evaluation:** maintain a hand-labeled gold set of event documents (≥ 50, spanning event types) and track field-level precision and recall per model/prompt version.

### 4.8 Prices, adjustment and returns (derived, L4)

1. **Raw prices** come from `price_daily`. Normalize the quote factor; keep the odd-lot market separate (default: do not mix odd-lot prices into the main series).
2. **Adjustment factors per instrument** from verified events:
   - cash: f = (P_cum − D) / P_cum, with P_cum = data-com close;
   - share-count: f = ratio_den / ratio_num;
   - rights: value the right at its traded price, or theoretically, as a cash-equivalent;
   - spin-offs: the value fraction to the child, from the first-day prices or the company's disclosed equity split (record which).
3. **Products (all derived, rebuildable, versioned by input snapshot):**
   - **back-adjusted price series** (for charting and compatibility; documented as non-stable over time);
   - **forward total-return index**, gross and net-of-withholding variants (JCP 15% and, from 2026, dividend withholding where applicable to the owner's situation via the tax engine), with explicit reinvestment assumption (ex-date close vs payment date; default ex-date close, configurable);
   - **lineage-aware total return across graph edges** (e.g., holding BRML3 through its merger into the successor continues the series).
4. **Golden integration test.** Recompute the 17-stock portfolio from §13.1. Its stated result is roughly +37% total return, gross, buy-and-hold, from 2025-10-02 to 2026-10-16, against the Yahoo cross-check.
   - The system's figure must be within a documented tolerance.
   - Every per-instrument difference must be explained by named events.

### 4.9 Fixed income and indexer data (inputs to valuation)

- **Calendar:** ANBIMA calendar, with `du` between any two dates computed from `calendar_day.du_index`.
- **CDI:**
  - daily rates from BCB SGS / B3, stored as published (percent per annum, 2 decimals);
  - the daily factor follows the official B3/CETIP TDI convention, including truncation/rounding rules (verify the exact rule; implement with `Decimal` and unit-test against published accumulated factors);
  - % of CDI products compound `1 + p·((1+CDI)^(1/252) − 1)` per business day.
- **Selic:** daily realized rate and the Copom target series.
- **IPCA:** monthly index number (not just the % change) from IBGE SIDRA; projections from ANBIMA for pro-rata.
- **VNA:** computed for NTN-B/NTN-C and cross-checked against published values.
- **Curves:** store as published (parameters and vertices). Fitting our own curves is L4 and optional.
- **Tesouro:** price/rate tables plus title rules (coupon dates, coupon rates: NTN-F 10% a.a., NTN-B 6% a.a., paid semiannually as (1+c)^(1/2) − 1).
- **Credit:** ANBIMA indicative rates where available; otherwise flag the instrument as curve-marked only.

### 4.10 Funds data specifics

- Quota series are the return series for funds (net of fees). Come-cotas reduces the holder's quota count and is modeled in the ledger, not in the quota series.
- Bridge the CVM 175 transition so a class's history connects to its predecessor fund where economically continuous; document the bridging rule.
- **Look-through:** CDA holdings resolved to `instrument_id` allow exposure aggregation across funds (e.g., the owner's total exposure to an issuer or indexer). Track the CDA publication lag in knowledge time.

### 4.11 Data quality framework

1. **Schema contracts** at L2 (types, nullability, enums, ranges) using a schema library (Pandera or equivalent) or DuckDB constraints. Contracts are versioned with connectors.
2. **Semantic checks** at L3:
   - prices > 0;
   - high ≥ max(open, close) ≥ min(open, close) ≥ low;
   - volume ≥ 0;
   - quotas positive and continuous;
   - rates in plausible ranges;
   - balance-sheet identity (assets = liabilities + equity) within rounding;
   - dates on business days where required.
3. **Temporal checks:**
   - gaps in expected daily series vs calendar;
   - stale values (unchanged beyond plausible length);
   - spikes (robust z-score on returns, using the median absolute deviation).
4. **Cross-source reconciliation matrix** (each pair produces `dq_finding` rows):
   - COTAHIST close ↔ Yahoo raw close (tolerance in ticks);
   - B3 events ↔ CVM IPE documents ↔ Yahoo dividends/splits;
   - Tesouro Transparente ↔ ANBIMA secondary rates;
   - own VNA ↔ published VNA;
   - own CDI accumulation ↔ published accumulated factors;
   - fund NAV ↔ sum of CDA holdings (approximate);
   - owner ledger ↔ Área do Investidor positions (exact).
5. **`dq_finding` table:** `finding_id`, `check_id`, `severity` (info/warn/error/blocker), `entity refs`, evidence refs, `status` (open/acknowledged/resolved/won't-fix), `resolution_note`, `resolved_by`, timestamps.
6. **Coverage reports:** per source, dataset and period: expected vs present, quarantined counts, freshness (last successful fetch, last reference date).
7. **Blocking policy:** blocker-severity findings on an instrument mark its derived outputs as `unreliable` in exports (§8) rather than silently excluding it.
8. **Golden fixtures:** curated real-world cases committed as small test fixtures, each with expected outcomes:
   - ITUB3's 2025 bonificação (103:100);
   - SLCE3's 9:8 bonus;
   - RADL3 51:50;
   - EGIE3 3.5:2.5;
   - GRND3's large 2025 payout;
   - a merger (e.g., ARZZ3 → AZZA3);
   - a ticker rename (e.g., VIIA3 → BHIA3);
   - a delisting (e.g., Carrefour Brasil, CRFB3);
   - a BDR migration (JBS);
   - a subscription right;
   - a fund that adapted to CVM 175;
   - an NTN-B coupon date.

   Verify each case's facts during recon. If one is misremembered, replace it with a verified equivalent.

### 4.12 Ingestion mechanics

- **Connector interface:** `discover()` (what exists, and for which reference dates) → `fetch(spec)` (writes raw + manifest) → `parse(raw) → L2 frames` → `validate()` → `load()`.
  - Each connector has a version, a recon note, layout docs and fixtures.
- **Modes:**
  - `backfill(range)`: resumable, checkpointed;
  - `incremental()`: since the last reference date;
  - `snapshot_today()`: for ephemeral sources.
- **Politeness:** per-source rate limits, a descriptive generic User-Agent (no personal email), exponential backoff with jitter, conditional requests (ETag/If-Modified-Since) where supported, local caching. Respect robots.txt and terms; unofficial endpoints are flagged and isolated.
- **Scheduling:** Windows Task Scheduler (document the setup), invoking one CLI entrypoint (`fin ingest daily`). The daily job must tolerate the laptop being off: on the next run it detects and catches up missed reference dates where the source allows, and logs unrecoverable gaps for ephemeral sources.
- **Owner inbox:** a watched folder (`inbox/`) for manual exports (Área do Investidor, notas de corretagem, statements, contracts). Files are hashed into raw on ingest; the original files are left untouched.
- **Secrets:** none required for public sources; any future credentials go in OS keychain or env vars, never in the repo.
- **Observability:**
  - structured logs (JSON lines) per run;
  - `ingest_run` table (start, end, status, counts, errors);
  - a `fin status` command that prints freshness, coverage and open blockers.

### 4.13 Reconnaissance protocol (before any connector)

For each source, produce `docs/sources/<source_id>.md` containing:
1. official URL(s), access method, terms/licensing notes, tier;
2. dataset list with granularity, history depth, update cadence, publication lag;
3. exact file layouts and field dictionaries, with links to the official layout docs and sample rows;
4. known quirks: encodings (often Latin-1 / Windows-1252), pt-BR decimal and date formats, scale factors, schema changes over time with the dates they happened;
5. identity fields available and how they map to §4.3.2 schemes;
6. a small committed fixture (≤ 1 MB) of real data for tests;
7. open questions.

Do not write a parser for a layout that has not been confirmed against a real file.

---

## 5. Ledger and tax layer

- **Double-entry ledger** in L3:
  - `account` (custody accounts per broker/bank/exchange, cash accounts, tax payable/receivable, fees, income);
  - `transaction` (owner action or system-generated event application);
  - `posting` (account, instrument, quantity, amount, currency; postings sum to zero per transaction in value terms);
  - `lot_basis` (average cost per instrument per custody account, Brazilian *preço médio*; keep lot detail too for analysis).
- **Sources:** notas de corretagem, Área do Investidor exports, statements, contracts. Corporate events are applied automatically from the verified event graph to the owner's holdings.
- **Reconciliation:** the end-of-day positions implied by the ledger must match the Área do Investidor positions exactly, for every custodied instrument, at every export date. Mismatch is a blocker finding.
- **Tax engine:** versioned rules with validity dates (`tax_rule` table: rule code, parameters, `vt_from`, `vt_to`, legal reference). It covers:
  - swing trade 15% with the R$20k monthly stock-sales exemption (shares only);
  - day trade 20%;
  - FII/Fiagro gains 20%, with distributions exempt under conditions;
  - ETF rules;
  - BDR rules;
  - the fixed-income regressive table and IOF;
  - come-cotas (May/November; long vs short-term rates);
  - JCP 15% withholding;
  - Lei 15.270/2025 dividend withholding above R$50k/month per paying company, from 2026;
  - Lei 14.754/2023 for offshore holdings;
  - crypto rules;
  - loss carry-forward by category;
  - DARF computation outputs.

  Every rule needs a legal reference and unit tests with worked examples. Laws change: rules are data, not code branches.
- **Outputs:** realized gains per month and category, tax due, the annual IRPF support schedules (bens e direitos, rendimentos isentos, tributação exclusiva).

---

## 6. Valuation engine (L4)

Three modes, one engine:
1. **Observed price:** the latest valid close or quota.
2. **Model price:** cash-flow schedule + discount curve + spread. Used for Tesouro intraday/marks, debentures, CRI/CRA and untraded bank paper.
3. **Formula accrual:** indexer accrual for CDI/Selic/IPCA/poupança products per contract.

Report both **curve value** (marcação na curva) and **market value** (marcação a mercado) where they differ, with a clear label. Valuation outputs carry their method, inputs (curve snapshot id, spread source) and a staleness flag.

---

## 7. Analytics (L4) — scope and stance

**Stance:**
- Risk and exposures are estimable; expected returns are not.
- Avoid sample-covariance mean-variance optimization, technical indicators and price-direction prediction.

**Deliverables:**
- **Performance:** time-weighted and money-weighted returns (XIRR), against benchmarks (CDI, Ibovespa total return, IMA-B, IFIX), gross and net of tax.
- **Exposure:** by asset class, indexer (CDI / IPCA / prefixado / FX), issuer (with fund look-through), sector, duration buckets, credit (FGC-covered vs not), liquidity (days to liquidate), NEFIN factor betas.
- **Risk:**
  - volatility and covariance with shrinkage (linear and nonlinear);
  - factor-model covariance;
  - drawdowns;
  - historical and filtered-historical VaR/expected shortfall;
  - stress scenarios: parallel and non-parallel curve shocks, inflation surprises, BRL shocks, equity crash replays.
- **Forecasting** (nuisance quantities only):
  - time-series foundation models (e.g., the Chronos, TimesFM, Moirai and TiRex families; choose after a local benchmark) for volatility, liquidity, fund flows and payout amounts;
  - walk-forward evaluation with CRPS/pinball loss against naive baselines (EWMA volatility, seasonal naive).

  For rates and inflation, use market curves and Focus expectations as the forecast.
- **Bayesian hierarchical models** (NumPyro/PyMC) where partial pooling helps (e.g., fund manager skill).
- **Text:** local embeddings over filings and documents (§4.3.6) for retrieval, to feed the export layer.

---

## 8. Export layer (L5) — dossier for the external LLM

- **Format:** a Markdown report plus attached Parquet/CSV tables, generated by `fin export dossier --as-of <date>`.
- **Contents:**
  - **IPS** (Investment Policy Statement: the owner's goals, horizons, liquidity needs, constraints), maintained by the owner as a versioned file;
  - holdings and valuation (with method labels);
  - performance against benchmarks;
  - exposures and risk;
  - upcoming events (payouts, maturities, coupons, tax dates);
  - changes since the previous dossier;
  - open data-quality findings affecting any number;
  - questions the owner wants adjudicated.
- **Rules:**
  - every figure carries an as-of date and source/method;
  - numbers are computed by the system (the LLM should not need to do arithmetic on raw series);
  - forecasts are labeled as distributions, never as facts;
  - unreliable items are labeled, not hidden.
- **Optional later:** a read-only MCP server over `catalog.duckdb` exposing curated views, so a chat client can query the system directly. It is out of scope until the dossier works.

---

## 9. Repository, engineering standards and documentation

```
/                       CLAUDE.md, PLAN.md, README.md, pyproject.toml (uv)
src/fin/
  reference/            calendar, units, source registry
  ingest/<source>/      connectors (discover/fetch/parse/validate/load)
  core/                 canonical model, identity resolution, event graph
  quality/              checks, reconciliation, findings, coverage
  derive/               adjustment, TR indices, positions
  ledger/               transactions, postings, basis, reconciliation
  tax/                  rule engine and rules
  valuation/            curves, cash flows, pricing
  analytics/            risk, exposures, performance, forecasting
  export/               dossier builder
  llm/                  OpenAI-compatible client, extractor, embeddings
  cli.py                `fin` entrypoint (Typer or argparse)
tests/                  unit, property-based (Hypothesis), integration, golden
docs/
  DECISIONS.md          dated architecture decisions (ADR-style, short)
  sources/              one recon note per source
  data_dictionary/      generated from schemas: every table, column, unit, meaning
  runbooks/             backfill, rebuild, scheduler setup on Windows
data/                   (git-ignored) zones from §4.2
inbox/                  (git-ignored) owner documents
```

- **Code quality:**
  - type hints everywhere; strict type checking (pyright or mypy);
  - ruff for lint and format;
  - `Decimal` or exact rationals for money, ratios and rates where exactness matters (event ratios, tax, ledger); floats only in analytics.
- **Tests:**
  - every connector has fixture-based parser tests;
  - every invariant in §4.1 has at least one test;
  - property-based tests for the event graph (value conservation), ledger balance and calendar arithmetic;
  - golden tests from §4.11.8 and §4.8.4.
- **Generated data dictionary:** column-level documentation (pt-BR and English descriptions, units) generated from schema definitions; CI-style local check that every table is documented.
- **Rebuild test:** `fin rebuild --from-raw` reproduces L2–L4 byte-identically or with a documented set of nondeterministic fields.

---

## 10. Build order (dependency-ordered stages with exit criteria)

**Stage A — Foundations**
- Repo scaffold, CLAUDE.md, uv, CLI skeleton, logging, `ingest_run`, manifest, raw content-addressed store, source registry, ANBIMA calendar.
- **Exit:**
  - raw store round-trips;
  - calendar `du` matches published examples;
  - rebuild command exists.

**Stage B — Reconnaissance**
- Recon notes and fixtures for every P source in §4.4. Begin the daily snapshot jobs for ephemeral sources immediately; they are the only stage-B code that runs before recon of all sources finishes.
- **Exit:**
  - every domain has a verified P source or an owner decision recorded in §12;
  - snapshot jobs are running.

**Stage C — Exchange-traded core**
- COTAHIST (full history), B3 instrument registry, CVM cadastro/FCA, identity resolution, `price_daily`, universes.
- **Exit:**
  - point-in-time universe test passes;
  - ticker-change and reuse tests pass;
  - coverage report shows full trading-day coverage.

**Stage D — Corporate events**
- B3 events backend, CVM IPE index, LLM extractor with gold set, event graph, verification suite, unexplained-gap scan.
- **Exit:**
  - golden event fixtures pass;
  - gap scan backlog is triaged;
  - the §4.8.4 portfolio recomputation is within tolerance.

**Stage E — Rates, curves, macro**
- BCB SGS, Focus, PTAX, IBGE SIDRA, B3 reference rates and settlements, ANBIMA ETTJ, projections, VNA, NEFIN.
- **Exit:**
  - CDI accumulation equals published factors;
  - VNA equals published VNA;
  - curve snapshots load for every business day in range.

**Stage F — Funds**
- CVM daily reports, cadastro (pre and post CVM 175), CDA, FII/Fiagro reports.
- **Exit:**
  - CVM 175 bridging tests pass;
  - look-through for a sample fund reconciles to NAV within tolerance.

**Stage G — Government bonds and credit**
- Tesouro Transparente, ANBIMA secondary data, debenture/CRI/CRA reference and terms.
- **Exit:** Tesouro PU recomputed from rate matches published PU.

**Stage H — Fundamentals and documents**
- DFP/ITR/FRE facts with versions, standardized metrics, shares outstanding, document text and embeddings.
- **Exit:**
  - point-in-time fundamentals query test passes, with restatement handled;
  - balance identity checks pass.

**Stage I — Ledger and tax**
- Inbox ingestion, notas de corretagem parsing, Área do Investidor reconciliation, tax engine.
- **Exit:**
  - ledger equals Área do Investidor positions exactly;
  - tax worked examples pass.

**Stage J — Valuation**
- All three modes, with labels.
- **Exit:** every owner holding has a value with method, inputs and staleness.

**Stage K — Analytics**
- Performance, exposures, risk, forecasting benchmarks.
- **Exit:** walk-forward evaluation reports exist; no forecast is used without beating its naive baseline.

**Stage L — Export**
- Dossier generator.
- **Exit:** the owner reviews a dossier and accepts the format.

Stages E–H depend on A–C but not on one another, and may proceed in any order once Stage D's identity and event machinery exists.

---

## 11. Working agreement for Claude Code

1. **Verify before you build.** Fetch real files, read the official layout documents, and commit fixtures. Never invent field layouts, endpoint parameters or codes from memory.
2. **When a source is unavailable**, blocked, changed or paywalled, record it in the recon note and DECISIONS.md, and propose alternatives. Do not silently substitute an unofficial source as primary.
3. **Prefer explicitness over cleverness** in the data layer: typed schemas, exact numerics, small pure functions, named checks.
4. **Never drop data silently.** Quarantine, count, report.
5. **Keep each change small and test-backed.** Run the relevant tests before declaring a step done. Use plan mode for any change touching §4.1 invariants or the canonical schema.
6. **Update docs with code:** recon notes, data dictionary, DECISIONS.md, runbooks.
7. **Owner-facing text** (CLI messages, reports, dossiers) is in Brazilian Portuguese, with financial terms as used in the Brazilian market. Code, identifiers and internal docs are in English.
8. **Ask the owner only for owner decisions** (§12) and for access to his personal documents. Decide engineering defaults yourself and record them.
9. **Respect source terms.** Throttle requests. No CAPTCHA bypassing, no credential sharing, no scraping behind logins without the owner performing the login.

---

## 12. Open questions for the owner

1. Paid sources: is any budget acceptable (e.g., ANBIMA Feed, a commercial B3 data vendor), or is the project strictly free-source?
2. Brokers, banks and exchanges currently and historically used (to scope statement parsers).
3. How far back the owner's personal ledger should start (first transaction).
4. Whether offshore and crypto holdings exist now or are anticipated.
5. Whether intraday data matters at all (default: no, beyond archiving what is free).
6. Preferred reinvestment assumption for total-return series (default: ex-date close).
7. Whether a GUI is wanted later (default: CLI plus exported reports).

---

## 13. Appendices

### 13.1 Reference portfolio for the golden test

A portfolio posted on r/investimentos on 2025-10-02 (weights as shown, renormalized from 96.8% legible):

| Ticker | Weight | Ticker | Weight |
|---|---|---|---|
| VALE3 | 3.0 | HYPE3 | 6.8 |
| PETR4 | 6.5 | FLRY3 | 6.1 |
| WEGE3 | 5.4 | ABEV3 | 5.3 |
| ITUB3 | 6.0 | PSSA3 | 7.0 |
| B3SA3 | 6.0 | SLCE3 | 5.6 |
| LREN3 | 5.6 | AGRO3 | 5.9 |
| GRND3 | 5.0 | MDIA3 | 5.4 |
| RADL3 | 5.7 | PRIO3 | 5.8 |
| EGIE3 | 5.7 | | |

Prior estimate from Yahoo adjusted closes, buy-and-hold, 2025-10-02 → 2026-10-16:
- total return about +37.2% (gross);
- price return about +28.5%;
- Ibovespa (points) +42.4%;
- CDI +14.9%.

The system must reproduce these within tolerance and explain every per-instrument difference.

### 13.2 Glossary pointer

The owner maintains a glossary of Brazilian market terms (data com, ex-date, JCP, bonificação, cisão, VNA, du/252, come-cotas, FGC, marcação a mercado/na curva…). Use these terms consistently in owner-facing output.
