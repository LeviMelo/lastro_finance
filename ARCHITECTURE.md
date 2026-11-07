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

## 3. Module map (`src/fin/`)

| module | job |
|---|---|
| `__init__.py` | version |
| `config.py` | the data home and its zones |
| `cli.py` | `fin`: `ingest`, `status`, `verify-raw`, `rebuild --from-raw` |
| `schema.py` | `Contract`, `Column`, `Rule`: typed columns with unit and pt/en meaning; conform and quarantine split (ADR-0005) |
| `store/` | L1 and the operational tables |
| `store/raw.py` | content-addressed raw store |
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
| `ingest/snapshots.py` | archive-only connectors for the ephemeral sources (ADR-0007) |
| `reference/` | L0 reference data |
| `reference/calendar.py` | `calendar_day` build and the `Calendar` API (`du`, shifts) (ADR-0006) |
| `reference/sources.py` | loads and validates `reference/sources.toml`, the source registry |
| `core/`, `quality/` | empty packages, Stage C/D |

## 4. Invariants as implemented

- Raw immutability: `store/raw.py` (read-only bit, verify on re-put, `fin verify-raw`).
- Provenance: `schema.PROVENANCE` columns on every staging contract.
- Quarantine, never drop: `Contract.split`; counts on the run.
- Rebuild: `fin rebuild --from-raw`, byte-identical on 2026-11-07.
- Calendar: `reference/calendar.py` only.
- Ephemeral archive: `fin ingest daily`; `fin status` blocks on an unarchived ephemeral source.
