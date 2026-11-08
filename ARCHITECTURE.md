# ARCHITECTURE.md

**The map of the code.** Read the code when the two disagree, then correct this file. The design intent is PLAN.md
§3–§4; this file says what exists. Written 2026-11-07 (Stage A).

## 1. The shape

```text
sources ─► ingest/<connector>.discover ─► fetch.Fetcher ─► store/raw (L1 bytes, content-addressed)
                                                  └──────► store/manifest (L1 index, one row per fetch)
raw + manifest ─► connector.parse ─► schema.Contract.split ─► staging/ (L2)  +  quarantine/
staging ─► connector.derive ─► core/ (L3)        e.g. core/reference/calendar_day
every step inside one store/runs.IngestRun: run id, JSON-lines log, counts in/out/quarantined, errors
```
`fin rebuild --from-raw` replays parse → split → derive from the manifest alone (ADR-0004).

## 2. Persistent objects (under the data home, `data/` or `FIN_DATA_HOME`)

| path | what | mutability |
|---|---|---|
| `raw/<sha[0:2]>/<sha>.<ext>` | every fetched payload, byte for byte | write-once, read-only (ADR-0002) |
| `manifest/part-<run>.parquet` | one row per fetch: request, status, validators, reference date, run | append-only parts (ADR-0003) |
| `runs/part-<run>.parquet` | `ingest_run`: start/end, status, counts, errors | append-only parts |
| `logs/<run>.jsonl` | structured log of a run | append-only |
| `staging/<source>/<dataset>/<partition>/<sha>.parquet` | L2, source-shaped, with provenance | rebuildable |
| `quarantine/…` (same layout) | rows that broke a contract rule, with `reject_rules` | rebuildable |
| `core/reference/calendar_day/calendar_day.parquet` | the business-day calendar | rebuildable |
| `raw/<sha[0:2]>/<sha>.<ext>.zsd` | a re-sent file stored as a delta of its previous version | write-once (ADR-0014) |
| `core/instrument/instrument.parquet`, `core/instrument_identifier/instrument_identifier.parquet` | exchange-traded instruments and their time-ranged ISIN, B3 code and tickers | rebuildable (ADR-0015) |
| `core/corporate_event/corporate_event.parquet` | dividends, JCP, FII income, bonuses, splits, rights, with sources and grade | rebuildable (ADR-0016) |
| `derived/adjustment_factor/adjustment_factor.parquet` | split and cash factors per instrument and ex-date | rebuildable |
| `quality/dq_finding/<check>.parquet` | data-quality findings, one file per check; status from `fin/quality/resolutions.toml` | rebuildable (ADR-0022) |
| `catalog.duckdb` | views only | rebuilt by `fin catalog` (ADR-0017) |
| `core/share_count/share_count.parquet` | shares per filing, in units | rebuildable (ADR-0020) |
| `core/fund_lineage/fund_lineage.parquet` | CVM 175 class → legacy predecessor CNPJ, with the rule | rebuildable (ADR-0025) |
| `core/instrument_link/instrument_link.parquet` | edges between instruments | rebuildable (ADR-0019) |
| `core/issuer/issuer.parquet`, `core/issuer_instrument/issuer_instrument.parquet` | companies by CNPJ and their instruments | rebuildable (ADR-0018) |
| `core/tesouro_bond/tesouro_bond.parquet`, `core/tesouro_price_daily/tesouro_price_daily.parquet` | Tesouro Direto bonds 2004– and daily rates/PUs | rebuildable |
| `core/price_daily/year=YYYY.parquet` | spot and odd-lot sessions per unit, 1986– | rebuildable (ADR-0015) |
| `staging/yahoo_intraday/bar/symbol=<s>/` | 5-minute bars (tier U), archived daily from 2026-11-07 | rebuildable |
| `staging/b3_cotahist/quote/year=YYYY/<sha>.parquet` | COTAHIST records, 1986–, one file per raw zip and year | rebuildable |
| `staging/<source>/{observation,definition}/…` | series values and metadata as each payload served them (SGS, Ipeadata, SIDRA, Tesouro VNA) | rebuildable |
| `staging/cvm_dfp_itr/<dataset>/form=<f>/year=<y>[/statement=<st>_<con>]/<sha>.parquet` | company statements DFP 2010–, ITR 2011– | rebuildable |
| `staging/b3_fundosnet/{distribution/id_block=N,listing/all}/<sha>.parquet` | FII/Fiagro distributions 2016-11– and listing rows; one small file per notice (~8 KB) | rebuildable |
| `staging/tesouro_transparente/price_rate/all/<sha>.parquet` | Tesouro Direto rates and PUs 2004-12-31–, one full snapshot per daily file | rebuildable |
| `core/series_observation/source=<id>.parquet` | every series value with period, unit and version (ADR-0013) | rebuildable |
| `core/series_definition/source=<id>.parquet` | latest name, frequency and unit per series | rebuildable |

## 3. Module map (`src/fin/`)

| module | job |
|---|---|
| `__init__.py` | version |
| `config.py` | the data home and its zones |
| `catalog.py` | `catalog.duckdb`: views over the Parquet zones, `fundamental_fact` and `price_adjusted` on read (ADR-0017); macros `universe(d, cls)` and `valuation(d)` (ADR-0021) |
| `cli.py` | `fin`: `ingest`, `status`, `verify-raw`, `reparse <sources>`, `compact-raw`, `compact-staging`, `catalog`, `quality`, `export dossier`, `rebuild --from-raw` |
| `analytics/risk.py` | volatility, drawdown, beta to the Ibovespa, sector exposure of a portfolio's realised path |
| `export/dossier.py` | `fin export dossier`: the PLAN §8 dossier (Markdown + Parquet) from a portfolio file (ADR-0026) |
| `quality/findings.py` | named checks → `dq_finding`; review status from `quality/resolutions.toml` (ADR-0022) |
| `schema.py` | `Contract`, `Column`, `Rule`: typed columns with unit and pt/en meaning; conform and quarantine split (ADR-0005) |
| `store/` | L1 and the operational tables |
| `store/raw.py` | content-addressed raw store; zstd at rest; deltas of previous versions (ADR-0014) |
| `store/compact.py` | re-encode stored versions as deltas; merge small staging files (ADR-0014) |
| `store/journal.py` | append-only tables: fsynced JSON-lines journal per run, sealed to Parquet |
| `store/manifest.py` | the manifest schema, canonical request identity, redaction |
| `store/runs.py` | `IngestRun`, crash recovery |
| `store/lock.py` | OS file lock telling live runs from crashed ones |
| `store/tables.py` | Parquet writing (zstd, row groups, atomic replace) |
| `ingest/` | connectors and the pipeline |
| `ingest/http.py` | polite HTTP client: per-host spacing, backoff with jitter, Retry-After, User-Agent |
| `ingest/fetch.py` | `FetchSpec` → raw + manifest, conditional requests, absent statuses |
| `ingest/base.py` | `Connector` interface (`discover`, `follow`, `parse`, `derive`), `run_connector`, `reparse` |
| `ingest/registry.py` | source → connector, the daily job's list, ephemeral sources not archived |
| `ingest/anbima_calendar.py` | ANBIMA holidays → staging `holiday` → core `calendar_day` |
| `ingest/snapshots.py` | archive-only connectors for the ephemeral sources (ADR-0007) and for files replaced in place (Tesouro, NEFIN) |
| `ingest/context.py` | the context catalogue (`reference/context_series.toml`) → one generated archive connector per source, cadence per entry (ADR-0011) |
| `ingest/alternates.py` | archive connectors for the routes that close data gaps: SND, Fundos.NET, BCB SGS, Ipeadata, Tesouro VNA, the `pyield_data` mirror, Yahoo (ADR-0010) |
| `ingest/series.py` | series payloads (SGS JSON and SOAP metadata, Ipeadata OData, SIDRA, Tesouro VNA workbooks, Treasury/NY Fed/Cboe CSVs, SDMX-CSV with the sources' unit codelists) → staging `observation`/`definition` → core `series_observation`/`series_definition`, versioned (ADR-0013) |
| `ingest/cvm_statements.py` | CVM DFP/ITR zips → staging `statement_line` (every account line, value as written with its scale), `document` (every version and its delivery date), `share_capital` |
| `ingest/cvm_rad.py` | CVM RAD: superseded DFP/ITR versions (statements XML without its PDFs, or the four statement members of the legacy nested zip as an `szip`) → staging `statement_line` (the open-data contract) and `share_capital` |
| `ingest/b3_fixed_income.py` | B3 BDI fixed-income OTC tables with history from `drp.b3.com.br` (Trade per trade since 2023-03-13, SaleOff, Stock) → staging `fi_trade`, `fi_settlement`, `fi_stock` |
| `ingest/snd_pu.py` | SND PU Histórico (daily PU of every debenture since issue, one file per ticker) → staging `debenture_pu` |
| `ingest/cftc.py` | CFTC Commitments of Traders (3 reports) → staging `position`, long |
| `ingest/cvm_fca.py` | FCA index, `geral` (company identity, no contact data) and `valor_mobiliario` (securities with trading code, market, segment, dates) → staging `document`, `company`, `security` |
| `ingest/cvm_fre.py` | FRE index, `capital_social` and the treasury row of `posicao_acionaria` → staging `document`, `capital_social`, `treasury` |
| `ingest/pyield.py` | the pyield-data mirror (tier S): ANBIMA bond rates 2020–, B3 futures 2018–, NTN-B VNA → staging |
| `ingest/ptax.py` | BCB PTAX (Olinda OData): every currency 1984– → staging `quote`, `currency`; series `bcb_ptax:<CCY>:buy/sell` |
| `ingest/anbima_parsers.py` | ANBIMA ETTJ (Svensson parameters, vertices), VNA, debentures, government bonds, projections |
| `ingest/nefin.py` | NEFIN risk factors (market, SMB, HML, WML, IML, risk-free) |
| `ingest/b3_pr.py` | B3 PR files (BVBG.086.01 price report: trades, settlement, open interest; several snapshots per day merged) → staging `price_report` |
| `ingest/b3_taxaswap.py` | B3 reference rates (TaxaSwap TS files 2001–: DI, IPCA, FX curves by vertex) → staging `swap_rate` |
| `ingest/cvm_funds.py` | CVM FII monthly/quarterly/annual and FIAGRO monthly reports, fund daily NAV (`inf_diario`), fund holdings (CDA) → staging |
| `ingest/cvm_ipe.py` | CVM IPE yearly index → staging `document` (evidence for events) |
| `ingest/copom.py` | BCB Copom decision history → staging `decision` |
| `ingest/focus.py` | BCB Focus expectations (8 tables) → staging `expectation` |
| `ingest/fundosnet.py` | Fundos.NET notices → staging `distribution` (per Provento and kind, exact BRL per quota) and `listing` (delivery minute = knowledge time, version) |
| `ingest/b3_events.py` | B3 listed-companies backend: issuers, cash history, stock events, subscriptions; Yahoo chart events (tier U) |
| `ingest/intraday.py` | Yahoo 5-minute bars for the most traded shares and FIIs, Ibovespa and USD/BRL (tier U) |
| `ingest/cvm_fi_cad.py` | CVM fund register: legacy `cad_fi` and `cad_fi_hist` (long form), CVM 175 `registro_fundo_classe` → staging `fund`, `fund_history`, `registered_fund`, `registered_class`, `registered_subclass` (no directors, no person managers) |
| `ingest/tesouro.py` | Tesouro Direto `PrecoTaxaTesouroDireto.csv` → staging `price_rate` (exact decimals; 0,00 PU = not offered) |
| `ingest/b3_cotahist.py` | COTAHIST fixed-width → staging `quote` (exact decimals as quoted), line repair and quarantine (ADR-0008) |
| `reference/` | L0 reference data |
| `reference/calendar.py` | `calendar_day` build and the `Calendar` API (`du`, shifts) (ADR-0006) |
| `reference/sources.py` | loads and validates `reference/sources.toml`, the source registry |
| `core/` | core tables built from staging |
| `core/events.py` | corporate events (B3, Yahoo, Fundos.NET) merged and graded by the price move; derived adjustment factors; `adjusted_close` (ADR-0016) |
| `core/shares.py` | `share_count`: CVM share counts in units, unit inferred per filing (ADR-0020); FRE counts 2010– (ADR-0021) |
| `core/links.py` | `instrument_link`: ticker and name continuity across ISIN changes, B3 cross-asset events (ADR-0019) |
| `core/issuers.py` | CVM register → staging `company` (no contact data) → core `issuer`, `issuer_instrument` (ADR-0018) |
| `core/funds.py` | `fund_lineage`: the legacy CNPJ a CVM 175 class continues (ADR-0025); `bridge_check` tests it on the daily quota |
| `core/tesouro.py` | Tesouro Direto → core `tesouro_bond`, `tesouro_price_daily` (versioned) |
| `core/equities.py` | COTAHIST → core `instrument`, `instrument_identifier`, `price_daily` (ADR-0015) |
| `quality/` | data-quality checks and findings (ADR-0022) |
| `export/` | exports for the external LLM: the dossier (ADR-0026) |
| `analytics/` | portfolio analytics: risk and exposure (Stage K) |

## 4. Invariants as implemented

- Raw immutability: `store/raw.py` (read-only bit, verify on re-put, `fin verify-raw`).
- Provenance: `schema.PROVENANCE` columns on every staging contract.
- Quarantine, never drop: `Contract.split`; counts on the run.
- Rebuild: `fin rebuild --from-raw`, byte-identical on 2026-11-07.
- Calendar: `reference/calendar.py` only.
- Ephemeral archive: `fin ingest daily`; `fin status` blocks on an unarchived ephemeral source.
