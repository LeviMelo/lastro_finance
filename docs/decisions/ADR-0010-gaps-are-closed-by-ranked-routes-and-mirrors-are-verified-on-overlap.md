## ADR-0010: A data gap is closed by the best verified route; a third-party mirror enters as tier S only after it equals the primary where both exist, and scraping is used only where the terms allow it

**Date:** 2026-11-07. **Status:** active.

**Context.** Recon on 2026-11-07 found history that the official sources no longer serve
([gap matrix](../evaluation/2026-11-07-data-gap-matrix.md)). Some gaps have a route that is not the primary source:
- a third-party mirror of the primary's data (`pyield_data`: ANBIMA bond rates from 2020);
- an official source of a neighbouring quantity (SND trade statistics instead of ANBIMA's debenture rates);
- an unofficial source (`yahoo_chart`: the bonificações B3's backend misses);
- scraping a public page or its JSON.

PLAN §4.4 says that tier-U facts never feed L3 alone, and PLAN §11 says to respect source terms.

**Decision.**
- **Routes are ranked:** official primary (P) > official secondary or a verified mirror of P (S) > unofficial (U)
  > paid (owner decision, OQ-10). The gap matrix records, for each gap, the best route and what it leaves open.
- **A mirror is tier S only after verification on overlap.** Where both the mirror and our archive of the primary
  exist, they must agree exactly; the comparison is repeated as a `dq_finding` check on every date both hold. Before
  the overlap the mirror's facts carry its `source_id`, never the primary's.
- **Unofficial facts are candidates.** A U event (Yahoo split or bonificação) adjusts nothing until it is matched to
  a P document (CVM IPE).
- **Scraping is a route like any other, with limits:**
  - only pages that render without login;
  - only where robots.txt and the published terms do not forbid it;
  - at most 1 request/s per host;
  - a Cloudflare or JavaScript challenge, a CAPTCHA or an HTTP 429 ends the attempt; none is bypassed.
- **Excluded by these limits:**
  - ANBIMA: its terms forbid spiders and data mining (termos de uso §2.4, §8.2), and ANBIMA Data needs a token;
  - Investing.com: its terms forbid storing the data, and it answers a Cloudflare 403;
  - Stooq: it answers a JavaScript challenge.

**Alternatives.**
- *Primary-only*: rejected. It leaves 2020–2026 bond rates, FII distributions and the missed bonificações blind,
  when routes exist that can be verified.
- *Promote a mirror to P on agreement*: rejected. Agreement on six days does not make a third party the publisher.

**What would reverse it.** The primary's history becoming free (ANBIMA, B3), or a mirror diverging from the
primary on overlap. In that case the mirror is demoted to U and the matrix row is reopened.
