## ADR-0017: The warehouse is a DuckDB file of views over the Parquet zones; reshaped staging is a view, not a copy

**Date:** 2026-11-07. **Status:** active. Implements PLAN §4.2's query layer (`fin/catalog.py`, `fin catalog`).

**Decision.**
- `data/catalog.duckdb` holds **views only**: about 270 KB, rebuilt in seconds, never stale against the files.
  - The daily job rebuilds it.
  - A view whose files do not exist yet is skipped.
- **Views:**
  - core: `instrument`, `instrument_identifier`, `price_daily`, `series_observation`, `series_definition`,
    `corporate_event`;
  - derived: `adjustment_factor`;
  - views over staging: `fundamental_fact`, `fii_distribution`, `intraday_bar`;
  - derived on read: `price_adjusted` (split-only and total-return closes).
- **`fundamental_fact` is a view.** It applies the reporting scale (`value_brl` = value × 1,000 for MIL), joins
  each version's delivery date (`received_on`, the knowledge date) and normalises the CNPJ. A core copy would
  duplicate 66.8 M lines (ADR-0014).
- **Every scan disables hive detection.** Partition folders such as `statement=BPA_con` otherwise shadow the column
  of the same name: found on the first build, when `statement` read `BPA_ind`.

**Measured.** Itaú consolidated total assets per DFP 2023–2025 (R$ 2.54 / 2.85 / 3.07 trillion), with the version
and delivery date, in 1.5 s over all 575 statement files.

**Alternatives.**
- *Load tables into DuckDB*: rejected. It would be a second copy, and stale after every ingest.
- *Materialise `fundamental_fact` in core*: rejected. It is a copy whose only change is a scale multiplication.
