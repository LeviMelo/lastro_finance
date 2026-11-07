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
