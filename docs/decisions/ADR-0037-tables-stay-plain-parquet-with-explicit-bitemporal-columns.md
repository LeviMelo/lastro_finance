## ADR-0037: Tables stay plain partitioned Parquet with explicit bitemporal columns (no DuckLake)

**Date:** 2026-11-09. **Status:** active. Resolves OQ-2 (PLAN §4.2 table-format decision).

**Context.**
- PLAN §4.2 asked for a choice between plain Parquet with DuckDB views and DuckLake (snapshots, time travel), plain
  Parquet being the default.
- Built so far on plain Parquet:
  - 65 sources, ~7 GB of staging, the core and derived zones;
  - the catalog (`catalog.duckdb`, views only);
  - rebuilds from raw;
  - point-in-time questions answered from the columns: `kt_published_at` and `kt_first_seen_at` on every row, RAD
    restatement versions (ADR-0027), ALFRED vintages.

**Decision.** No DuckLake. History lives in raw (immutable, content-addressed) and in the knowledge-time columns.
Staging and core are rebuildable from raw, so a table snapshot would only store again what raw already holds.

**Consequences.**
- No extra catalog database or extension to keep in step with DuckDB versions.
- Time travel is a filter on `kt_*`, not on a table version. A query "as known on date D" uses the bitemporal
  columns, as the panel export does (ADR-0032).
