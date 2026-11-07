# How measurements are made

- **Independent figures only.** A check against the system's own assumptions passes by construction. Ground truth is
  what another party published or what a second source states: BCB's accumulated CDI factors, B3's and CVM's own
  totals and record counts, the documented ratio of a corporate event, the owner's custody statements (Área do
  Investidor), Yahoo/brapi only as cross-checks (tier U/S).
- **Real data, committed.** Fixtures are byte-exact excerpts of real responses (`tests/fixtures/<source_id>/`, each
  with a README giving URL, fetch date and SHA-256). Synthetic data is used only for mechanics (hashing, journaling,
  retries), never to establish a fact about a source.
- **Regime.** Every entry names the commit (or "uncommitted, on top of <sha>"), the data home and the date.
- **Counts, not impressions.** Rows in/out/quarantined, objects, bytes, days covered against days expected.
