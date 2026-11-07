# The context catalogue is archived from its first served date: 21 sources, about 1,250 objects, 0 errors left after two fixes (2026-11-07)

Regime: e57213f plus the uncommitted `ingest/context.py` and `reference/context_series.toml`. Data home `data/`,
2026-11-07 17:56–18:30 UTC. Commands: `fin ingest <sources> --mode backfill` (runs 20261107T175639Z-64b5a4,
20261107T181800Z-5eca8d). Counts are from the run summaries.

| group | sources | objects | depth |
|---|---|---|---|
| Brazil macro | `bcb_sgs` (60 series), `ibge_sidra` (11 tables), `ipeadata` (16), `bcb_copom` | ~90 | SGS 1944– (IGP-DI), IPCA 1979–, GDP 1996Q1–, Copom 1996– |
| Expectations | `bcb_focus`, 8 survey tables × 27 survey years | 216 | 2000– |
| Brazil markets | `b3_index_levels` (23 indices × years), `anbima_ima`, `cepea` (8), `anp` | 584 | Ibovespa 1968–; IMA today only |
| Global rates | `us_treasury` (61 year files), `nyfed`, `ecb` (7), `bis` (2) | 72 | Treasury 1990–, BIS policy rates 1954– |
| Risk, commodities, positioning | `cboe` (5), `eia` (2), `worldbank_cmo`, `imf`, `oecd`, `cftc_cot` (51) | 62 | VIX 1990–, WTI 1986–, Pink Sheet 1960– |

**Two errors fixed by measurement.**
- Focus: BCB's OData service rejects `+` for a space with HTTP 400 and accepts `%20`. The client encoded `+`, so the
  filter is now written into the URL with `%20` (216 errors before, 0 after).
- SGS 226, 195 and 25 (TR, poupança) carry daily start dates, so whole-history requests get HTTP 406. They moved to
  10-year windows.

**Still unverified.**
- One SGS request answered an unconditional HTTP 304 with an empty body (SGS 188, a known quirk,
  docs/sources/bcb_sgs.md). The object was already held from the first run.
- Raw grew from 3.9 GB to 4.0 GB.
- No parser exists yet for these files (ADR-0007): units, scales and sign conventions are recorded per entry in
  docs/sources/context_br.md and context_global.md, and are checked when each parser is written.
