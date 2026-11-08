## ADR-0012: Collecting public market data for the owner's personal use is the personal use the sources' general terms allow; collection stays polite and is never redistributed

**Date:** 2026-11-07. **Status:** active. Owner decision; resolves OQ-24.

**Context.** On 2026-11-07 two clauses were read that conflict with automated collection:
- **B3**, on the BDI page, the pesquisapregao page and the market-data history hub: *"é expressamente vedada a
  coleta automatizada, inclusive por meio de ferramentas de inteligência artificial, para quaisquer finalidades,
  comerciais ou não, próprias ou de terceiros"*. B3's general terms allow *"uso exclusivamente pessoal"* and forbid
  commercial use and redistribution.
- **ANBIMA**'s terms forbid spiders and data mining (§2.4, §8.2) and allow unaltered public content with credit
  (§8.3).

**Decision (owner, 2026-11-07).**
- LASTRO automates what the owner could fetch by hand for the management of the owner's own portfolio. That is the
  personal, non-commercial use the general terms allow. The B3 and ANBIMA connectors keep running.
- **Conditions that keep it so:**
  - per-source request limits with adaptive backoff (the blanket 1 request/s first written here is replaced
    by ADR-0023);
  - only public pages, no login;
  - no CAPTCHA or bot challenge bypassed;
  - nothing redistributed, published or sold;
  - exports to an LLM carry derived figures for the owner's own discussion, not bulk source data.
- The owner expects these extractors to break as the sites change. A broken connector is a run error and a
  `fin status` blocker, never a silent gap.

**Alternatives.**
- *Stop and download by hand into the inbox*: rejected by the owner. It reproduces the failure mode of the owner's
  previous attempt.
- *Ask B3 for written permission*: not needed in the owner's reading.

**What would reverse it.** A source blocking or contacting the owner, a change in the owner's use (anything shared or
commercial), or terms that withdraw personal use.
