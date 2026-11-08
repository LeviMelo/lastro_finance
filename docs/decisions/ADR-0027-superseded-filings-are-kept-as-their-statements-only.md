## ADR-0027: Superseded CVM filings are recovered from RAD and kept as their statements only

**Date:** 2026-11-08. **Status:** active. Settles OQ-24. `ingest/cvm_rad.py`, `FetchSpec.extract`
(`ingest/fetch.py`).

**Context.**
- CVM's open-data DFP/ITR zips keep only the latest version of each filing: 6,137 filings were restated, which
  leaves 7,558 superseded versions.
- RAD still serves every version, as a zip of 2.6–35 MB (mean 7.75 MB) with no byte ranges. Most of it is the PDF of
  the filing, which also sits inside the statements XML as base64 text.
- The owner asked for a way that blows up neither storage nor memory.

**Decision.**
- **Download and reduce at once.** Each version is downloaded whole, one zip in memory per download slot, and reduced
  before archiving by `FetchSpec.extract`.
- **What the raw store keeps:** the statements XML with the text of every `<ImagemObjetoArquivoPdf>` removed (the
  empty element is kept). That is 35 % of the member and 31 KB under zstd.
- **The record:** a JSON object holds the full download's sha256 and size, plus every member's name, size and
  CRC. A later re-download can be verified against it.
- **A deliberate exception to "raw is the bytes as fetched".** The dropped part is a rendering of the same filing,
  served again by the same URL, so the original remains provable.
- **The parser emits the open-data `statement_line` contract.** Verified on 33 XML-era filings (52,032 open-data
  lines): 30 match exactly. The other 3 differ only in DMPL column labels, which open data assigns by position from
  a fixed list, so the XML's own labels are the correct ones (docs/sources/cvm_rad_versions.md §5).

**Limits.**
- Only versions from doc id 108951 (2021-10-07) are in the XML layout: 1,953 of 7,558.
- The earlier 5,605 come as a nested `.dfp`/`.itr` zip of entity dumps. Those are marked held, so they are never
  re-downloaded, and they wait for a legacy parser.
