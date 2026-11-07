## ADR-0008: An object that cannot be parsed is an error of the run, a line that cannot be read is quarantined whole; a repaired line says so

**Date:** 2026-11-07. **Status:** active.

**Context.** The first parse of B3's `COTAHIST_A2026.ZIP` (fetched 2026-11-07, 3,429,676 records) failed on one line:
line 2,072,135 (`FR0T5L`, "FROTA OCEÂNI") is 246 bytes, because B3 wrote the Â as UTF-8 into a latin-1 file. The
parser raised (correctly), but the same exception aborted `fin rebuild --from-raw` for every source. Raw is immutable,
so one bad object would have blocked every later rebuild, and in `fin ingest` it skipped the source's remaining files.

**Decision.**
- `load` runs per raw object inside `_load_isolated`: a parse failure is recorded on the run (where, message,
  `raw_sha256`) and the run continues; the command exits non-zero. A rebuild keeps the state it produced and reports
  the objects in error.
- Inside a file, a line is **repaired only when the repair is provable**: here, when its bytes decode as UTF-8 to exactly
  the record length. Its `raw_locator` then ends `;decoded=utf-8`.
- A line that cannot be read is written whole to quarantine (`unparsed_line`, with its reason and locator) and counts
  toward the file's record total, so the trailer check still holds. Structural surprises (no header, unknown record
  type) still fail the file.

**Evidence.** After the change, a rebuild from raw ran with 0 objects in error. The A2026 line parses with
`short_name = "FROTA OCEÂNI"` (`tests/unit/test_b3_cotahist.py`, fixture `COTAHIST_A2026_utf8_excerpt.TXT`).

**What would reverse it.** Errors that are systematic rather than local (a layout change), where failing the whole
source early is cheaper than recording thousands of object errors; the run record makes that visible either way.
