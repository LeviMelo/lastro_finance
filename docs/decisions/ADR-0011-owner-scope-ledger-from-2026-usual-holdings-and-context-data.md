## ADR-0011: The owner's scope: the ledger starts in 2026, holdings are stocks, FIIs, ETFs and Tesouro Direto, and economic context data is a first-class domain

**Date:** 2026-11-07. **Status:** active. Answers OQ-12 and OQ-13 (PLAN §12.3, §12.4).

**Context.** The gap matrix (2026-11-07) chased every gap PLAN's asset scope implies, back to the earliest date. The
owner answered on 2026-11-07:
- the first transaction is in 2026;
- the holdings will be the usual ones: stocks, FIIs, ETFs, Tesouro Direto;
- analysis must be grounded in economic and financial context (company statements, futures, commodities, indices,
  macro), not in prices alone.

PLAN §1.2 lists context data in one line and §4.4 names five macro sources, with no catalogue of series.

**Decision.**
- **Priority 1: what the owner's holdings and ledger need from 2026 on.** Prices and events of stocks, FIIs and
  ETFs; FII distributions; Tesouro Direto prices; CDI, IPCA and VNA; the daily archive of ephemeral sources.
- **Priority 2: history for analysis**, as deep as free sources allow:
  - prices since 1986;
  - statements since 2010;
  - curves since 2000;
  - macro series.
  A gap here is a limit on analysis, not a defect of the ledger.
- **Priority 3: classes the owner does not hold** (debentures, CRI/CRA, crypto, offshore): archived where it is cheap
  (already wired), not pursued further until the owner holds them.
- **Context data is a domain of its own.** It gets a catalogue of named series (Brazilian macro, rates and
  expectations, global rates, FX, commodities, risk indicators), each mapped to a free source and verified like any
  other source (PLAN §4.13).
- **CVM company filings** (DFP, ITR, FRE, FCA, IPE) are archived from 2026-11-07, because CVM keeps only the latest
  version of each filing. The cadence is in `ingest/alternates.py`.

**Alternatives.**
- *Everything at the same priority* (PLAN read literally): rejected, because it spends effort on gaps that cannot
  affect a ledger starting in 2026.
- *Context data left to the analysis stage*: rejected, because the series need the same identity, units and
  knowledge time as prices.

**What would reverse it.** The owner acquiring a class of priority 3, or importing holdings from before 2026.
