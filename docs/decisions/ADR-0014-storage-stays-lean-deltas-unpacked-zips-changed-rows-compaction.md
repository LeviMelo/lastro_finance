## ADR-0014: Storage stays lean: re-sent files are stored as deltas, re-shipped zips as member deltas, staging keeps changed rows, small files are compacted

**Date:** 2026-11-07. **Status:** active. Amends ADR-0002 and ADR-0009 (how raw bytes are encoded at rest).

**Context.**
- The owner was burned before by redundant raw/processed copies and by caches keyed on raw bytes.
- On 2026-11-07, 15.6 GB was downloaded and 3.9 GiB stored. About 3 GB of that is archives the sources ship already
  compressed (zip, B3's self-extracting curve files); most of the rest is distinct daily data.
- Real redundancy was found in three places:
  - **sources that resend their whole history:** Tesouro sends 14 MB a day for one new day;
  - **CVM's weekly yearly zips:** about 4–5 GB a year if kept whole;
  - **staging:** it kept a full copy of every snapshot, one file per raw object; Fundos.NET alone had 17,384 files.

**Decision.**
- **Raw deltas.** A new version of a file is stored as `<sha256>.<ext>.zsd`: a zstd frame compressed against its
  previous version.
  - The previous version is the same source, dataset and locator.
  - A delta is kept only when it is under half the plain encoding.
  - Chains are cut every 16 versions.
  - The original bytes are rebuilt and hashed before commit. `read` and `verify` are unchanged for callers.
  - `fin compact-raw` re-encodes stored versions the same way: the new file is verified before the old one goes.
- **Unpacked zips.** With `FetchSpec.unpack_members` (CVM's yearly zips), each member is stored as its own raw object
  and as a delta of its previous version.
  - A JSON record keeps the zip's sha256 and size, and each member's name, CRC-32, size and sha256.
  - The members are the source's bytes exactly; the compressed zip bytes are transport and are not kept.
  - Zips archived before this decision stay as they are.
- **Changed rows only.** For connectors with `dedup_staging`, a new version of a file stages only rows not identical
  to a row of the previous version. A value that returns (A→B→A) is still staged, and core versions are unchanged.
  - Verified: `series_observation` has 585,075 rows before and after.
  - `reparse` clears the source's staging first.
- **Compaction.** `fin compact-staging` merges a partition's per-object files into one. The daily job runs it.
- **Keys are content.** Raw is keyed by the content's hash. Staging rows keep `raw_sha256` as provenance, but what is
  kept is decided by the row's content.

**Measured (docs/evaluation/2026-11-07-storage-and-price-daily.md).**
- Tesouro: a daily version as a delta is 41 KiB instead of 2.2 MiB.
- Fundos.NET staging: 17,384 files and 129.5 MiB became 11 files and 1.3 MiB.
- The B3 registry gains little: every line carries the report date, so a delta is 81 % of plain zstd and is not kept.

**Alternatives.**
- *Delete raw once parsed*: rejected. Raw is the only thing a parser fix can be replayed from (PLAN invariant 1), and
  the ephemeral sources cannot be fetched again.
- *Keep CVM zips whole*: rejected for the growth above.
- *Reverse deltas (newest whole)*: rejected. They rewrite the previous object at every fetch, which breaks write-once.

**What would reverse it.** A read path made too slow by chains: shorten `KEYFRAME`.
