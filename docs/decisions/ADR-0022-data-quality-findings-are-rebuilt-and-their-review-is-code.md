## ADR-0022: Data-quality findings are rebuilt from the zones; their review status is code

**Date:** 2026-11-07. **Status:** active. `fin/quality/findings.py`, `fin/quality/resolutions.toml`, `fin quality`.

**Context.** Invariant 7 ("reconcile, don't trust") and PLAN §4.11.5 ask for `dq_finding` records with a status.
Until now disagreements were only written into source notes, or graded inside a table (event `status`).

**Decision.**
- **Named checks.** Each check is a pure function of the zones. `fin quality`, and the daily job after its
  ingest, write one file per check: `quality/dq_finding/<check>.parquet`. These files are rebuildable: no wall-clock
  time goes into a row, and the zone is part of `fin rebuild`.
- **Stable ids.** `finding_id` = F + 12 hex of sha256(check | entity | valid date). The same disagreement keeps its
  id across rebuilds.
- **Review is code.** The status (open, acknowledged, resolved, wont_fix) and its note live in
  `fin/quality/resolutions.toml`, in git. A finding not listed there is open. Nothing is ever picked or dropped
  silently: a finding never changes the data it is about.
- **Severity.** info (unproven, adjusts nothing), warn (a disagreement), error (a value that breaks computations,
  e.g. a zero price), blocker (reserved for PLAN §4.11.7).
- Catalog view `dq_finding`.

**First checks (2026-11-07).** 111 findings:
- `vna_ntnb_vs_ipca`, 1, acknowledged: 2014-02, where Tesouro's VNA implies a Jan-2014 IPCA index of 3836.38 and
  IBGE prints 3836.37 in SIDRA and in its historical series;
- `ohlc_inconsistent`, 1, acknowledged: BGIP4 2021-05-18, one trade of R$ 2,224.00 with every price 0 in COTAHIST.
  A first version that also checked the average flagged 6,520 sessions: PREMED includes trades the high/low do
  not, so the average is not checked;
- `link_price_jump`, 9, open;
- `stock_event_unproven`, 100;
- `share_count_unit_mismatch`, 0. It found 5 before FRE anchored the units (ADR-0020 addendum).
