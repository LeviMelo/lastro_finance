## ADR-0013: Series are one long, versioned table; each row carries its source's period and unit, and a series without a definition is quarantined

**Date:** 2026-11-07. **Status:** active. Implements PLAN §4.3.4 `series_observation` / `series_definition`.

**Context.** About 1,000 macro, rate and index series arrive from SGS, Ipeadata and SIDRA (and later the global
sources). Each source dates periods differently: SGS writes `01/09/2026` for September, SIDRA `202602` for a quarter
or for a rolling quarter's last month. Units sit in separate metadata (SGS, Ipeadata) or on every row (SIDRA).
Sources revise without keeping vintages.

**Decision.**
- **Staging is source-shaped.** A row keeps the date and the value as written (`period_text`, `value_text`). A
  missing value keeps its marker and its meaning in `missing_reason`: `...`, `..`, `X`, JSON null, or a reason the
  parser states (a VNA of 0 after a group matured). Any other text quarantines.
- **Definitions are archived raw, like data:**
  - SGS from its SOAP `getUltimoValorXML`, because CKAN lacks 11 of our codes;
  - Ipeadata from `Metadados('<code>')`;
  - SIDRA from the payload itself.
  - Each is re-requested monthly.
  - Where a payload carries no unit (Treasury, Cboe, NY Fed, the VNA workbooks), the parser declares it and cites
    the source note that verified it.
  - Where a payload carries a unit code (SDMX: ECB, BIS, OECD), the source's codelist is archived monthly and the
    core step writes `label (code)`.
- **Core rows join the latest definition.**
  - `vt_reference` follows the frequency: `2024-03-15`, `2024-03-15..2024-04-14` (a stated end, as for TR),
    `2024-03`, `2024Q1`, `2024`, `2024-01..2024-03` (rolling quarter).
  - The unit is the source's text.
  - A series with no definition, or a date off its frequency's grid, is quarantined.
- **Versions.** A value enters core when first seen. It enters again only when a later payload changes it.
  `kt_first_seen_at` and the provenance point to that payload.
- **Ids** are `<source_id>:<source code>` (`bcb_sgs:433`, `ibge_sidra:7060/v63/c315/7169`). Cross-source identity
  (SGS 433 = SIDRA 1737 v63) is a reconciliation, not a merge.
- **Error pages.** An HTML error page that a source served with HTTP 200 is `NotData`: counted, never a parse error.
  Fetchers name the content types they expect.

**Alternatives.**
- *A curated unit table in TOML*: rejected. The sources publish units, so copying them by hand is a second source of
  truth.
- *Wide tables per source*: rejected. The data layer would need one reader per table.

**What would reverse it.** A source whose units change inside one series' history, which would need the unit on the
definition version and not only the latest.
