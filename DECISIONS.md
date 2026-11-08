# DECISIONS.md

The index of this project's decisions. Each decision is one file under `docs/decisions/`, named
`ADR-NNNN-<slug>.md`; read the index, then the entries you need.

**Append-only.** Never edit a decision's substance; to reverse one, write a new ADR that says what it supersedes. A
later dated note on an entry's status line is allowed. Each entry states the context with its evidence, the decision,
the alternatives where they were weighed, and **what evidence would overturn it**. Only settled decisions are recorded.

| ADR | date | decision | status | relations |
|---|---|---|---|---|
| [ADR-0001](docs/decisions/ADR-0001-documentation-follows-the-pharos-model.md) | 2026-11-07 | Documentation follows the PHAROS model; PLAN.md stays the reference of intent | active |  |
| [ADR-0002](docs/decisions/ADR-0002-raw-is-content-addressed-and-the-manifest-records-reconfirmations.md) | 2026-11-07 | Raw objects are content-addressed and read-only; the manifest also records reconfirmations (304) | active | amended by ADR-0009 |
| [ADR-0003](docs/decisions/ADR-0003-run-tables-are-journaled-per-run.md) | 2026-11-07 | The manifest and ingest_run are journaled per run and sealed as Parquet parts; a live run holds a lock | active |  |
| [ADR-0004](docs/decisions/ADR-0004-staging-is-one-file-per-raw-object-and-rebuilds-are-byte-identical.md) | 2026-11-07 | Staging holds one file per (dataset, partition, raw object), stamped with the fetching run; a rebuild is byte-identical | active |  |
| [ADR-0005](docs/decisions/ADR-0005-contracts-are-declared-columns-with-units.md) | 2026-11-07 | Table contracts are declared columns with unit and meaning; a type mismatch raises, a rule failure quarantines | active |  |
| [ADR-0006](docs/decisions/ADR-0006-the-calendar-is-anbimas-file-and-du-counts-start-not-end.md) | 2026-11-07 | The calendar is built from ANBIMA's holidays file alone; du counts business days in [start, end) | active |  |
| [ADR-0007](docs/decisions/ADR-0007-ephemeral-sources-are-archived-before-they-are-parsed.md) | 2026-11-07 | Ephemeral sources are archived daily before their parsers exist; B3's BDI replaces the old settlement page | active |  |
| [ADR-0008](docs/decisions/ADR-0008-a-bad-object-or-line-is-isolated-never-fatal.md) | 2026-11-07 | An object that cannot be parsed is an error of the run, a line that cannot be read is quarantined whole; a repaired line says so | active |  |
| [ADR-0009](docs/decisions/ADR-0009-large-text-raw-is-zstd-compressed-at-rest.md) | 2026-11-07 | Raw text payloads of 64 KiB or more are zstd-compressed at rest; their name and their bytes stay the original's | active | amends ADR-0002 |
| [ADR-0010](docs/decisions/ADR-0010-gaps-are-closed-by-ranked-routes-and-mirrors-are-verified-on-overlap.md) | 2026-11-07 | A data gap is closed by the best verified route; a mirror is tier S only after it equals the primary on overlap; scraping only where the terms allow | active |  |
| [ADR-0011](docs/decisions/ADR-0011-owner-scope-ledger-from-2026-usual-holdings-and-context-data.md) | 2026-11-07 | The owner's scope: ledger from 2026; stocks, FIIs, ETFs, Tesouro Direto; economic context data is a domain of its own | active |  |
| [ADR-0012](docs/decisions/ADR-0012-personal-use-covers-automated-collection-of-public-pages.md) | 2026-11-07 | Collecting public market data for the owner's personal use is the personal use the general terms allow; polite, never redistributed | active | amends ADR-0010 |
| [ADR-0013](docs/decisions/ADR-0013-series-are-one-versioned-long-table-with-the-sources-own-units.md) | 2026-11-07 | Series are one long, versioned table with the source's period and unit on every row; no definition, no publication | active |  |
| [ADR-0014](docs/decisions/ADR-0014-storage-stays-lean-deltas-unpacked-zips-changed-rows-compaction.md) | 2026-11-07 | Storage stays lean: re-sent files as deltas, re-shipped zips as member deltas, staging keeps changed rows, small files compacted | active | amends ADR-0002, ADR-0009 |
| [ADR-0015](docs/decisions/ADR-0015-instrument-identity-from-isin-and-price-daily-per-unit-in-the-currency-of-the-day.md) | 2026-11-07 | An exchange-traded instrument is an ISIN with time-ranged tickers; price_daily is per unit in the currency of the day with an exact fraction to BRL | active |  |
| [ADR-0016](docs/decisions/ADR-0016-corporate-events-are-merged-across-sources-and-graded-by-the-price-move.md) | 2026-11-07 | Corporate events are merged across B3, Yahoo and Fundos.NET and graded by the price move; adjustment factors come from graded events only | active |  |
| [ADR-0017](docs/decisions/ADR-0017-the-warehouse-is-duckdb-views-over-parquet.md) | 2026-11-07 | The warehouse is a DuckDB file of views over the Parquet zones; reshaped staging is a view, not a copy | active |  |
| [ADR-0018](docs/decisions/ADR-0018-an-issuer-is-a-cnpj-linked-to-instruments-through-b3-roots.md) | 2026-11-07 | An issuer is a CNPJ, linked to its instruments through B3's CVM code → ticker root | active |  |
| [ADR-0019](docs/decisions/ADR-0019-instrument-links-from-ticker-continuity-and-b3-cross-asset-events.md) | 2026-11-07 | Instruments are linked by ticker continuity and by B3 events issuing another asset; only same-class events adjust prices | active |  |
| [ADR-0020](docs/decisions/ADR-0020-share-counts-get-an-inferred-unit-per-filing.md) | 2026-11-07 | CVM share counts get an inferred unit per filing, anchored to B3's current count | active |  |
| [ADR-0021](docs/decisions/ADR-0021-valuation-is-a-point-in-time-catalog-macro.md) | 2026-11-07 | Valuation (market cap, P/L, P/VP) is a point-in-time catalog macro over share counts, prices and statements | active |  |
| [ADR-0022](docs/decisions/ADR-0022-data-quality-findings-are-rebuilt-and-their-review-is-code.md) | 2026-11-07 | Data-quality findings are rebuilt from the zones by named checks; their review status is code (resolutions.toml) | active |  |
| [ADR-0023](docs/decisions/ADR-0023-request-limits-are-per-source-and-adaptive.md) | 2026-11-07 | Request limits are per source and adaptive; slow sources are fetched concurrently (replaces the blanket 1 request/s) | active |  |
