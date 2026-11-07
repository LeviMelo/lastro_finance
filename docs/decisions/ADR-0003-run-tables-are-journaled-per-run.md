## ADR-0003: The manifest and ingest_run are journaled per run and sealed as Parquet parts; a live run holds a lock

**Date:** 2026-11-07. **Status:** active.

**Context.** PLAN §4.2 asks for the manifest as Parquet with a DuckDB view, §4.12 for an `ingest_run` table. A run can
die mid-way (laptop sleep, crash), and two processes may run at once (the scheduled daily job and a manual backfill).

**Decision.**
- During a run each row is appended and fsynced to `<table>/_journal/<run_id>.jsonl`; on exit the journal becomes
  `<table>/part-<run_id>.parquet` with the table's fixed schema. Parts are never rewritten.
- A run holds an OS file lock (`runs/_locks/<run_id>.lock`) for its lifetime. `recover()`, called at every run start
  and by `fin status`, seals the journals of runs whose lock is free and marks those runs `crashed`.
- Run ids are `YYYYMMDDTHHMMSSZ-<6 hex>`: sortable and unique.

**Alternatives.** *One DuckDB file for operational tables*: rejected because a single writer would block the
concurrent daily job, and `catalog.duckdb` must hold nothing that cannot be rebuilt (PLAN §4.2).

**What would reverse it.** Part counts large enough to slow reads (thousands of runs), calling for a compaction that
keeps the rows unchanged.
