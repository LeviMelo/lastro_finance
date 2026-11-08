## ADR-0023: Request limits are per source and adaptive; slow sources are fetched concurrently

**Date:** 2026-11-07. **Status:** active. Replaces the "at most 1 request/s per host" of ADR-0010 and ADR-0012.

**Context.** PLAN §4.12 asks for per-source rate limits with backoff. I had written a blanket 1 request/s per host
instead, unmeasured, and enforced it sequentially. Fundos.NET serves one small XML per payout notice (about 36,600)
on a server that takes about 1-2 s per answer, so the backfill ran at about 0.5 notices/s: close to 20 hours. The
owner called the rule out as self-imposed.

**Decision.**
- `Connector.min_interval` (default 0.2 s) is the floor between request starts per host. It is adaptive: a 429 or
  5xx doubles the host's interval (up to 10 s), and each clean answer shrinks it back by 10 % toward the floor.
  Retry-After and jittered exponential backoff stay.
- `Connector.concurrency` (default 1) keeps that many downloads in flight ahead of the sequential archiving. The
  archive and the manifest are written in order, by one thread; only the network half runs in parallel.
- Fundos.NET: concurrency 8, floor 0.05 s.
- What stays fixed: a generic User-Agent, no personal data, no CAPTCHA bypass, no logins, conditional requests.
