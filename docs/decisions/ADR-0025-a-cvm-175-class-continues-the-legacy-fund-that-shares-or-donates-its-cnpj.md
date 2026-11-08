## ADR-0025: A CVM 175 class continues the legacy fund whose CNPJ it carries; the bridge is tested on the daily quota

**Date:** 2026-11-08. **Status:** active. Settles the bridging rule of PLAN §4.10 (`core/funds.py`,
`ingest/cvm_fi_cad.py`, `scripts/check_exit_criteria.py`).

**Context.** Under CVM Res. 175 a fund is registered with classes and subclasses. The register
(`registro_fundo_classe.zip`) links them (`ID_Registro_Fundo` → `ID_Registro_Classe` → `ID_Subclasse`) and dates the
adaptation (`Data_Adaptacao_RCVM175` on the fund); the legacy register (`cad_fi`, `cad_fi_hist`) holds the CNPJs that
existed before. Measured 2026-11-07: of the 91,046 funds, 45,035 have an adaptation date; 36,942 funds have exactly one class; 37,653 of the
37,803 classes of adapted funds carry the same CNPJ as their fund. The daily report keeps publishing the same CNPJ and
changes `TP_FUNDO_CLASSE` from the legacy type to `CLASSES - FIF`.

**Decision.** `core.fund_lineage` has one row per class with a legacy CNPJ (a CNPJ in `cad_fi` or `cad_fi_hist`):
- `same_cnpj` (27,399): class CNPJ = fund CNPJ. The class is the legacy fund.
- `class_own_legacy` (19): the class CNPJ is itself a legacy fund that became a class of another fund.
- `fund_single_class` (22): new class CNPJ, the fund's only class; predecessor = the fund CNPJ.
- `fund_multi_class` (21): new class CNPJ, several classes: the legacy fund was split. Listed, **not** claimed
  continuous.
A class with no legacy CNPJ is a new fund (`Data_Adaptacao_RCVM175` is filled for those too) and has no row.
`valid_from` = `Data_Adaptacao_RCVM175`; the daily report switches type a median 17 days later, so the test measures
the switch from the data (`TP_FUNDO_CLASSE` starting with `CLASSE`), not from the register.

**Test (`core.funds.bridge_check`).** Last legacy-typed row `L` of the predecessor before the first class-typed row
`F`: clean when at most 3 business days (ANBIMA calendar) lie between them and the quota moves at most 1 %; `moved`
when it moves more but within 5 robust sigmas of the fund's own daily moves; `jump` beyond; `gap` otherwise.

**Measured (2026-11-08, 20,217 testable bridges):** 18,590 clean (92 %), 1,381 moved, 182 jumps, 64 gaps: 98.8 %
continuous. Untestable: 5,521 without a legacy series (the legacy CNPJ never reported before the class type) and 1,723
without a class series. The criterion passes at the 98 % threshold set here (`scripts/check_exit_criteria.py`).
Failures are described in `docs/sources/cvm_fi_cadastro.md` §7.

**Alternatives.** Link by name (rejected: names change at adaptation); require equal CNPJ (rejected: loses the 41
umbrella cases); treat every class of a multi-class fund as the successor (rejected: a split has no single successor).

**Would overturn it.** A class whose register entry names its predecessor explicitly (CVM adding such a field), or the
daily report switching to a new CNPJ for adapted funds.
