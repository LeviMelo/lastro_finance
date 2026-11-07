# Of 19 data gaps against PLAN's scope, 11 are closed by a free verified route (4 of them through a mirror or an unofficial source), 5 are partly closed and 3 have no free route; no paid vendor verifiably sells the missing ANBIMA or B3 history to an individual (2026-11-07)

Regime: the third recon pass, by three Sonnet agents plus my own re-checks, 2026-11-07 15:00–16:00 UTC. Raw notes are
in the source notes listed below; ranking rules are in ADR-0010. "Wired" means archived by a connector today.
Verdict codes:
- **C**: closed (free, verified);
- **C-S** / **C-U**: closed through a secondary or unofficial route;
- **P**: partial;
- **O**: open (no free route).

| # | gap | best route found (verified) | verdict | state |
|---|---|---|---|---|
| 1 | ANBIMA government-bond rates before 2026-10-29 | `pyield_data` mirror, 2020-01-02 →, equal to our ANBIMA files on overlap; Wayback ~85 days 2012–18; Tesouro morning rates 2004 → as proxy (NTN-B, LFT within a few bp; prefixados 10–30 bp off) | C-S 2020 →; P before | wired (mirror backfilled) |
| 2 | ANBIMA debenture rates before 2026-10-29 | SND trade statistics 1993-11 → (realised trades, not indicative rates); Wayback 81 daily files 2013–19 | P | wired (SND backfill running) |
| 3 | Debenture terms and schedules | SND terms of 10,069 debentures since 1981, dead included; agenda future-only | C (terms), P (past events) | wired daily / weekly |
| 4 | CRI/CRA rates, ETTJ, IMA, ANBIMA projections history | none free. Substitutes: B3 TS curves 2000 → (held) for ETTJ; BCB Focus for projections | O | paid: ANBIMA Feed, price not published |
| 5 | IGP-M / IGP-DI index numbers | Ipeadata 1989-06 → / 1944 →, equal to ANBIMA's latest | C-S | wired daily |
| 6 | VNA NTN-B / NTN-C | Tesouro monthly tables 2000 →, recomputed exactly from IPCA / IGP-M | C | wired daily |
| 7 | B3 futures settlements and open interest 2018 → | PR files (OQ-20, disk) or `pyield_data` b3_futures (10 MB, 9 contracts) | C-S | wired (mirror) |
| 8 | B3 futures settlements before 2018 | none: legacy BM&F backend dead ("SQL Server does not exist"), 28 unlisted pesquisapregao prefixes absent, COTAHIST has no futures | O | paid: B3 UP2DATA On Demand, price not published |
| 9 | Business-day calendar 1986–2000 | BCB SGS 11/12 publication days; exact against ANBIMA on 2001–05 | C (derived) | wired; calendar code is OQ-22 |
| 10 | Index composition history | CVM CDA holdings of index ETFs (monthly, IBOV/IBXX/IBXL/SMLL/IDIV/IFIX…, 2018-06 →); B3's retro PDF of IBOV 2003–13 (2013 method, illustrative); BDI PDF: **compositions present in the full bulletin of 2024-09-02 (751 pages, 20.9 MB) and later, absent from 2022-03-01 (4 pages)**, start between the two not measured; B3's page forbids automated collection (OQ-24); GitHub IBOV ticker lists 2003–22 (U) | P | not wired: CDA parser (Stage C) |
| 11 | Stock events B3's backend misses | Yahoo has every known miss (U); CVM IPE proves each (P); Status Invest / Fundamentus give cash events with JCP labels (U) | C-U, verified through IPE | wired (Yahoo, 896 tickers) |
| 12 | B3 equity open interest and lending before 2026-10-07 | BDI PDF 2022-03 → (32 MB a day, OQ-20); before: none | P | owner (OQ-20) |
| 13 | FII / Fiagro distributions | Fundos.NET structured notices 2016-11-30 →, with minute knowledge time | C (2016 →) | wired (backfill running, ~10 h) |
| 14 | Instrument registry before 2018 | COTAHIST ticker / ISIN / class per year; FCA tickers from ~2018; no CNPJ history | P | Stage C |
| 15 | Fundamentals before 2010 | none on CVM (no IAN, DFP 2010 →, ITR 2011 →) | O | paid: Economatica (price not published) |
| 16 | Crypto (PLAN §1.2) | Binance bulk files (BTCUSDT 2017-08-17 →, BTCBRL 2020-10 →); Coinbase 2015 →; Foxbit 2021 →; Mercado Bitcoin API: Cloudflare 521 from both hosts (origin down; TLS and TCP fine): retry | C | not wired: OQ-13 |
| 17 | Offshore prices and events | Tiingo free tier (needs a token); SEC EDGAR submissions (200, no key); Yahoo (U). Stooq: JavaScript challenge | C (with token) | not wired: OQ-13, OQ-23 |
| 18 | PR file history 2018 → (settlements, OI) | PR backfill 10–15 GB (OQ-20); the mirror covers the 9 main contracts meanwhile | C | owner |
| 19 | NEFIN factors lag (last 2026-09-08) | NEFIN only; computable from COTAHIST once prices and universes exist | P | Stage F |

**Paid services (prices fetched 2026-11-07):**
- B3 UP2DATA: legal persons only. Access costs R$ 850.17 (indirect) or R$ 1,698.24 (direct) a month, plus R$ 283–425
  a month per dataset. UP2DATA On Demand's price is not published.
- ANBIMA Feed: "exclusive to members"; price not published.
- brapi Pro: R$ 1,399.90 a year, with dividends and splits > 10 years and fundamentals from 2009. It is an aggregator
  (tier U), and it does not close gaps 1, 4, 8 or 12.
- EODHD: US$ 19.99 a month, personal use; B3 coverage not verified.
- Dados de Mercado: rolling 5–10-year dumps; price not published.
- Economatica, ComDinheiro, Quantum: no published price.
- No vendor was found that sells ANBIMA rate history or pre-2018 B3 futures to an individual at a published price.

**Verified by me after the agents (not taken on their word):**
- the mirror's LTN row equals our ANBIMA file;
- Fundos.NET's oldest and newest notices and one XML;
- Yahoo's ITUB4 and SLCE3 events;
- the Mercado Bitcoin 521, with `curl -v`;
- the SND date parameters: the agent had them backwards; they are month/day/year (docs/sources/snd_debentures.md).
