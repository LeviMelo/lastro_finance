## ADR-0002: Raw objects are content-addressed and read-only; the manifest also records reconfirmations (304)

**Date:** 2026-11-07. **Status:** active.

**Context.** PLAN §4.1 invariant 1 and §4.2. Several sources rewrite files in place: CVM regenerates yearly zips for
about five years and its registries daily; ANBIMA corrects published bond-rate days
(docs/sources/cvm_cia_cadastro.md, docs/sources/anbima_titulos_publicos.md). CVM answers `If-None-Match` and
`If-Modified-Since` with 304 (measured 2026-11-07).

**Decision.**
- An object is stored once at `raw/<sha[0:2]>/<sha>.<ext>`, through a temporary file and an atomic rename, then marked
  read-only. Storing bytes already held verifies their size and is a no-op. `fin verify-raw` re-hashes everything.
- A request's identity is the SHA-256 of its canonical JSON (method, URL, params, body; credentials redacted). When the
  previous fetch of the same request has an ETag or Last-Modified, the next one is conditional.
- A 304 writes a manifest row pointing at the object already held, so the manifest says when a payload was last
  confirmed unchanged. A status a connector declares *absent* (e.g. 404 outside a rolling window) is logged, not an
  error; any other non-2xx is a run error and stores nothing.
- `kt_first_seen_at` of a fact is the earliest `fetched_at` of its raw object.

**What would reverse it.** A source whose 304s are unreliable (content changed without its validator changing), which
would call for unconditional fetches there.
