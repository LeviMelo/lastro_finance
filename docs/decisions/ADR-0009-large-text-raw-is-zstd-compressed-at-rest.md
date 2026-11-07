## ADR-0009: Raw text payloads of 64 KiB or more are zstd-compressed at rest; their name and their bytes stay the original's

**Date:** 2026-11-07. **Status:** active. Amends ADR-0002 (storage form only).

**Context.** The host disk had 50 GB free of 931 GB on 2026-11-07, against "tens of GB" planned (PLAN §2). The sources
found in recon that must be kept whole are mostly plain text served uncompressed. B3's InstrumentsConsolidatedFile and
TradeInformationConsolidatedFile are ~31 MB a day, ~11 GB for the 356 days served since 2025-06-10. The BDI JSON pages
and CVM's registries are also plain text.

**Decision.**
- An object whose extension is csv, txt, json, xml, html or tsv and whose size is ≥ 64 KiB is stored as
  `raw/<sha[0:2]>/<sha>.<ext>.zst` (zstd level 9, content size in the frame header).
- Its name is still the SHA-256 of the **original** bytes. `read`/`open` return the original bytes exactly, and
  `verify` re-hashes them.
- Archives (zip, xls, pdf, the self-extracting `.ex_`) and small objects are stored as they are. Objects written
  before this decision stay uncompressed; nothing is rewritten.

**Evidence.** On the first 22 B3 files archived (2026-11-07), 269.6 MB original took 20.2 MB on disk (13×).
`tests/unit/test_store.py` checks the exact round trip and the naming.

**Alternatives.**
- *Store as served*: rejected, because it would not fit the disk with the B3 backfill.
- *Compress whole zones with the filesystem* (NTFS compression): rejected, because it is weaker (~2×), host-specific,
  and invisible to the code.

**What would reverse it.** Read speed on large objects becoming a bottleneck for parsing (zstd decompresses at
> 1 GB/s, so this is unlikely), or a need to serve raw files to other tools directly.
