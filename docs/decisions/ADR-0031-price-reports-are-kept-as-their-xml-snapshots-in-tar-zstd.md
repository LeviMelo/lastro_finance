## ADR-0031: B3 Price Reports are kept as their XML snapshots in tar+zstd with long-distance matching

**Date:** 2026-11-08. **Status:** active. `ingest/b3_pr.py` (`extract_snapshots`, `snapshots`),
`B3PesquisaPregao` (`ingest/snapshots.py`), `ingest/fetch.py` (extracts run in the download threads).

**Context.**
- The owner approved the PR history 2018– (OQ-20) with storage as the constraint.
- A day's `PR<YYMMDD>.zip` is a zip holding a zip of 3–4 XML snapshots of the same day (21 MB each in 2018, 130 MB
  in 2026), 95–99 % byte-identical (b3_settlement_prices.md).
- As served, 2018–2026 would take ~11–15 GB.
- Measured on 2026-11-06, for one day:

| Stored form (lossless) | Size | CPU |
|---|---|---|
| Zip as served | 11.08 MB | — |
| 4 XML, zstd 19 each | 7.28 MB | 79 s |
| Patch chain (each XML against the previous) | 6.11 MB | 75 s |
| All in one stream, long-distance matching, level 15 | 5.06 MB | 3 s |
| Same, level 16, 256 MB window | **2.98 MB** | 36 s |
| Same, level 19, 2 GB window | 2.80 MB | 53 s |

Multi-threaded zstd loses the cross-snapshot matches (5.3 MB at any level).

**Decision.**
- **What is kept.** Each PR download keeps its XML snapshots byte for byte in a USTAR tar (fixed metadata, sorted
  names, so equal input gives equal bytes) compressed with zstd level 16, long-distance matching, window 2^28
  (`.tzst`).
- **The record.** A JSON record keeps the download's sha256 and size and the names, sizes, CRC-32s and dates of
  the outer and inner zip members, so the stored object can be tied to the exact download (ADR-0027 pattern).
- **Parallel work.** The compression runs in the download threads, 3 at once, about 1 GB of RAM each.
- **Reading.** The parser reads both forms. The 14 zips archived before this decision stay as they are (raw is
  immutable).
- **Checked.** The 2026-11-06 file round-trips: identical snapshots, identical staging (57,793 rows),
  deterministic bytes.

**Consequences.** The 2018–2026 PR history should take ~3 GB instead of ~11–15 GB. The zip container itself is
not kept, only its content and structure (as with ADR-0014's unpacked members).

**Would overturn it.** B3 changing the PR into a format the tar cannot hold byte-exact, or a need for the
container bytes themselves.
