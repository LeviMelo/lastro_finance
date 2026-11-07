## ADR-0004: Staging holds one file per (dataset, partition, raw object), stamped with the fetching run; a rebuild is byte-identical

**Date:** 2026-11-07. **Status:** active.

**Context.** PLAN §4.1 invariant 10 requires idempotent steps and L2–L4 rebuildable from L1 plus code;
`fin rebuild --from-raw` must reproduce byte-identically or document its nondeterministic fields (§9).

**Decision.**
- A parsed frame is written to `staging/<source>/<dataset>/<partition>/<raw_sha256>.parquet`, its quarantined rows to
  the same path under `quarantine/`. Parsing the same object again replaces the same file.
- `ingest_run_id` on a row is the run that **fetched** its raw object (its first manifest row), not the run that parsed
  it, so L2 content depends only on raw + code.
- An ordinary ingest does not re-parse an object already archived. `fin rebuild --from-raw` moves the rebuildable zones
  aside, re-parses every distinct object from the manifest, and restores the old zones on failure.
- Measured 2026-11-07: the rebuild reproduced every staging and core file byte for byte
  ([evaluation](docs/evaluation/2026-11-07-stage-a-first-daily-run.md)).

**What would reverse it.** Small files slowing scans (PLAN §4.2 warns against partitions under ~50 MB); a compaction
would then be a derived, rebuildable step over these files.
