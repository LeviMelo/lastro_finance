## ADR-0030: IMA index history comes from ANBIMA's "Série histórica" form, fetched on a fresh session per request

**Date:** 2026-11-08. **Status:** active. `ingest/context.py` (`ImaConnector`), `ingest/series.py` (`parse_ima_sh`),
`ingest/http.py` (`stateless`).

**Context.** The IMA figures existed only from 2026-10-29 (daily XML). The old IMA page `ima-sh.asp` posts to
`ima-sh-down.asp`, which serves the "Quadro Resumo" of any business day since 2001-12-04. The portfolio is not served
before the last 6 business days. The ASP server answers every request of one session with the first date asked (cookie).

**Decision.**
- `anbima_ima` gains the dataset `ima_sh_txt` (same source, same series ids as the XML): backfill asks every business day
  not held (6,251 files, 10 MB), a normal run the last 10 days.
- `Connector.stateless` / `PoliteClient(stateless=True)` drops cookies after each answer; the parser also refuses a file
  whose date is not the one asked, and a changed header.
- Two defects of the XML parser are fixed: `IMA-B 5+`/`IRF-M 1+` no longer share an id with `IMA-B 5`/`IRF-M 1`
  (`_mais`), and `market_value` is R$ mil, not BRL.
- Where the XML and the txt overlap (2026-10-29..11-06) both stay as versions; they differ only by rounding of PMR and yield.

**Consequences.** Index figures 2001-12-04 → are public and complete; the portfolio history stays a gap (docs/sources/context_br.md).
