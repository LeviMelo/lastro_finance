## ADR-0007: Ephemeral sources are archived daily before their parsers exist; B3's BDI replaces the old settlement page

**Date:** 2026-11-07. **Status:** active.

**Context.** PLAN §4.1 invariant 13 and §4.13 (no parser before a layout is confirmed on a real file) pull in opposite
directions for sources that serve only a short window. Recon on 2026-11-07 measured:
- **B3.** The `www2.bmf.com.br` settlement page redirects to the BDI app. B3 deactivated its public-data pages on
  2026-03-31; the data has been in BDI since 2025-12-15. BDI serves **21 business days** (2026-10-07 served,
  2026-10-06 empty). This contradicts PLAN §4.4, which names the old page.
- **ANBIMA government-bond indicative rates.** About **6 business days** are served, every older date is 404, and
  corrections are made in place. PLAN §4.4 does not mark this source as ephemeral.
- **CVM company and fund registries.** Current snapshots overwritten daily.

**Decision.**
- These sources have archive-only connectors (`src/fin/ingest/snapshots.py`, registry status `archiving`) run by
  `fin ingest daily`; parsers come later, from raw, once their layouts are confirmed.
- Windowed sources are re-planned from the calendar on every run, so a missed day is caught up while it is still in
  the window. ANBIMA's whole window is re-fetched daily to keep every corrected version; BDI re-fetches its last two
  days and skips days already held.
- `fin status` reports as a blocker every ephemeral source in the registry that the daily job does not archive.
- The daily job runs from Windows Task Scheduler (`scripts/schedule_daily.ps1`) once the owner approves registering it.

**What would reverse it.** A long-history route for any of these sources (under investigation: B3 `pesquisapregao`
BVBG files, ANBIMA Data, Internet Archive captures), which would make that source's daily job a convenience.
