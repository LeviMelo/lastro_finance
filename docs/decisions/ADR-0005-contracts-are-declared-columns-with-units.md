## ADR-0005: Table contracts are declared columns with unit and meaning; a type mismatch raises, a rule failure quarantines

**Date:** 2026-11-07. **Status:** active.

**Context.** PLAN §4.11.1 suggests Pandera or DuckDB constraints for L2 contracts. Invariants 8 and 11 require explicit
units and quarantine-never-drop. §9 requires a data dictionary generated from the schema definitions, with pt-BR and
English descriptions and units. Pandera carries no unit and no bilingual meaning.

**Decision.**
- A `Contract` (`src/fin/schema.py`) declares each table's columns (name, Polars dtype, nullability, unit, English and
  pt-BR meaning) and its named row rules (Polars expressions). Provenance columns are added to every staging contract.
- `conform` checks columns and dtypes exactly; a mismatch is a connector defect and raises.
- `split` applies nullability and rules; failing rows go to quarantine with `reject_rules` naming every rule broken,
  and the run records in/out/quarantined.
- The data dictionary is to be generated from these contracts.

**Alternatives.** *Pandera (polars backend)*: rejected as a second declaration of the same columns beside the one
that carries units and meanings; Polars' own schema comparison already does the type check.

**What would reverse it.** Checks Polars expressions cannot state (distribution tests), where a library would be added
for that job.
