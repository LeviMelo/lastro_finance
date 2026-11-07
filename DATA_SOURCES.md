# DATA_SOURCES.md

Verified facts about the sources LASTRO reads: **measured, not remembered**. The facts live in one recon note per
source, `docs/sources/<source_id>.md` (template `docs/sources/_TEMPLATE.md`, PLAN §4.13). This file indexes them and
keeps the facts that cut across sources. Where a note disagrees with PLAN.md, a brief or a code comment, the note wins
and the discrepancy is recorded (ADR-0001). Facts are dated by the recon that measured them; a source can change
without notice. The golden cases of PLAN §4.11.8, verified against three sources each:
[golden_events](docs/sources/golden_events.md).

Registry: `src/fin/reference/sources.toml`. `uv run fin status` shows freshness and blockers.

## Index

| source | institution | tier | window / history | status | note |
|---|---|---|---|---|---|
| `anbima_calendar` | ANBIMA | P | 2001–2099 | parsed | [note](docs/sources/anbima_calendar.md) |
| `anbima_titulos_publicos` | ANBIMA | P | **ephemeral: 6 business days** | archiving since 2026-10-29 | [note](docs/sources/anbima_titulos_publicos.md) |
| `anbima_ettj` | ANBIMA | P | **ephemeral: 6 business days** | archiving since 2026-10-29 | [note](docs/sources/anbima_ettj.md) |
| `anbima_vna` | ANBIMA | P | **ephemeral: 6 business days** | archiving since 2026-10-29 | [note](docs/sources/anbima_vna.md) |
| `anbima_debentures` | ANBIMA | P | **ephemeral: 6 business days** | archiving since 2026-10-29 | [note](docs/sources/anbima_debentures.md) |
| `anbima_projecoes` | ANBIMA | P | **ephemeral: latest values only** | archiving since 2026-11-07 | [note](docs/sources/anbima_projecoes.md) |
| `b3_bdi` | B3 | P | **ephemeral: 21 business days** | archiving since 2026-10-07 | [note](docs/sources/b3_settlement_prices.md) |
| `b3_instruments` | B3 | P | **since 2025-06-10, start may roll (OQ-19)** | archiving; served history backfilled | [note](docs/sources/b3_instruments.md) |
| `b3_pesquisapregao` | B3 | P | PR 2018-01-02–, TS 2000-01-14– | archiving daily since 2026-11-07 | [note](docs/sources/b3_settlement_prices.md) |
| `b3_reference_rates` | B3 | P | via TS files 2000–; web CSV since 2026-10-05 | archiving (as `b3_pesquisapregao` TS) | [note](docs/sources/b3_reference_rates.md) |
| `b3_index_portfolio` | B3 | P | **ephemeral: current composition only** | archiving since 2026-11-07 | [note](docs/sources/b3_index_portfolio.md) |
| `b3_cotahist` | B3 | P | yearly 1986–, daily 2014– | parsed (1986–2026) | [note](docs/sources/b3_cotahist.md) |
| `b3_company_events` | B3 | **U** | cash since 1995, incomplete for stock events | recon | [note](docs/sources/b3_company_events.md) |
| `cvm_cia_cadastro` | CVM | P | **ephemeral: today's snapshot** | archiving since 2026-11-07 | [note](docs/sources/cvm_cia_cadastro.md) |
| `cvm_fi_cadastro` | CVM | P | **ephemeral: today's snapshot** | archiving since 2026-11-07 | [note](docs/sources/cvm_fi_cadastro.md) |
| `cvm_fca` | CVM | P | 2010– (tickers from ~2018) | recon | [note](docs/sources/cvm_fca.md) |
| `cvm_fre` | CVM | P | 2010– | recon | [note](docs/sources/cvm_fre.md) |
| `cvm_dfp_itr` | CVM | P | DFP 2010–, ITR 2011– | recon | [note](docs/sources/cvm_dfp_itr.md) |
| `cvm_ipe` | CVM | P | 2003– | recon | [note](docs/sources/cvm_ipe.md) |
| `cvm_vlmo` | CVM | P | 2018– | recon | [note](docs/sources/cvm_vlmo.md) |
| `cvm_fi_inf_diario` | CVM | P | 2000– (real size from 2004) | recon | [note](docs/sources/cvm_fi_inf_diario.md) |
| `cvm_fi_cda` | CVM | P | 2005– | recon | [note](docs/sources/cvm_fi_cda.md) |
| `cvm_fii` | CVM | P | 2016– | recon | [note](docs/sources/cvm_fii.md) |
| `cvm_fie` | CVM | P | 2017– | recon | [note](docs/sources/cvm_fie.md) |
| `tesouro_transparente` | Tesouro Nacional | P | 2004-12-31– (file replaced daily) | archiving since 2026-11-07 | [note](docs/sources/tesouro_transparente.md) |
| `bcb_sgs` | BCB | P | full; ≤ 10-year windows for daily series | archiving (11, 12, 432, 1178, 4389) | [note](docs/sources/bcb_sgs.md) |
| `bcb_ptax` | BCB | P | 1984– in one call | recon | [note](docs/sources/bcb_ptax.md) |
| `bcb_focus` | BCB | P | 2000– | recon | [note](docs/sources/bcb_focus.md) |
| `ibge_sidra` | IBGE | P | IPCA number index (Dec-1993 = 100), monthly | recon | [note](docs/sources/ibge_sidra.md) |
| `nefin` | NEFIN-FEA/USP | S | 2001– (last date 2026-09-08) | archiving since 2026-11-07 | [note](docs/sources/nefin.md) |
| `snd_debentures` | SND | P | terms 1981– (snapshot), agenda future-only, trades 1993-11– | archiving | [note](docs/sources/snd_debentures.md) |
| `tesouro_vna` | Tesouro Nacional | P | VNA NTN-B / NTN-C monthly 2000– | archiving | [note](docs/sources/tesouro_vna.md) |
| `b3_fundosnet` | B3 | P | FII/Fiagro distribution notices 2016-11– | archiving | [note](docs/sources/b3_fundosnet.md) |
| `ipeadata` | IPEA (FGV) | S | IGP-M 1989–, IGP-DI 1944– | archiving | [note](docs/sources/ipeadata.md) |
| `pyield_data` | third-party mirror | S | ANBIMA bond rates 2020–, B3 futures 2018– | archiving (on demand) | [note](docs/sources/pyield_data.md) |
| `b3_index_levels` | B3 | P | daily closes of 23 indices, IBOV 1968– | archiving | [note](docs/sources/context_br.md) |
| `bcb_copom` | BCB | P | every Copom meeting 1996– | archiving | [note](docs/sources/context_br.md) |
| `anbima_ima` | ANBIMA | P | **ephemeral: latest day only** | archiving | [note](docs/sources/context_br.md) |
| `cepea` | CEPEA/ESALQ | S | agricultural indicators 1996– | archiving | [note](docs/sources/context_br.md) |
| `anp` | ANP | P | fuel prices monthly 2013– | archiving | [note](docs/sources/context_br.md) |
| `us_treasury` | US Treasury | P | par curve 1990–, real 2003– | archiving | [note](docs/sources/context_global.md) |
| `nyfed` | NY Fed | P | EFFR 2000–, SOFR 2018– | archiving | [note](docs/sources/context_global.md) |
| `ecb` | ECB | P | €STR 2019–, euro curve 2004–, FX 1999– | archiving | [note](docs/sources/context_global.md) |
| `bis` | BIS | P | policy rates 1954–, effective FX | archiving | [note](docs/sources/context_global.md) |
| `cboe` | Cboe | P | VIX and SKEW 1990– | archiving | [note](docs/sources/context_global.md) |
| `eia` | EIA | P | Brent 1987–, WTI 1986– | archiving | [note](docs/sources/context_global.md) |
| `worldbank_cmo` | World Bank | P | ~70 commodities monthly 1960– | archiving | [note](docs/sources/context_global.md) |
| `imf` | IMF | P | commodity prices monthly 1992– | archiving | [note](docs/sources/context_global.md) |
| `oecd` | OECD | P | leading indicators 1990s– | archiving | [note](docs/sources/context_global.md) |
| `cftc_cot` | CFTC | P | positioning weekly, files 2010– | archiving | [note](docs/sources/context_global.md) |
| `yahoo_intraday` | Yahoo | **U** | 5-minute bars, last ~60 trading days only; archived daily from 2026-11-07 | parsed (daily) | [note](docs/sources/yahoo_intraday.md) |
| `yahoo_chart` | Yahoo | **U** | splits ~2005–, dividends ~2007– | archiving (on demand) | [note](docs/sources/yahoo_chart.md) |

## Cross-source facts (2026-11-07)

- **Context data** (ADR-0011): the series catalogue is `src/fin/reference/context_series.toml`, one verified route per
  entry; Brazilian facts in [context_br](docs/sources/context_br.md), global in
  [context_global](docs/sources/context_global.md). No free route: PMI, FGV confidence suite, CDS, EMBI+ after
  2024-07, IMA history, long B3 investor-flow history.

- **Gaps and the routes that close them:** [gap matrix](docs/evaluation/2026-11-07-data-gap-matrix.md), ranked by
  ADR-0010. ANBIMA bond rates 2020– come from a verified mirror; IGP index numbers from Ipeadata; the VNA from
  Tesouro; FII distributions from Fundos.NET; B3's missed bonificações from Yahoo (U), proven through CVM IPE.

- **Where PLAN.md §4.4 is wrong or incomplete.**
  - B3's settlement and TxRef pages are gone; BDI keeps 21 business days (ADR-0007). The long-history routes are
    B3's `pesquisapregao` files:
    - PR (BVBG.086: settlements, open interest) from 2018-01-02. A zip holds 3–4 same-day snapshots; merge them,
      because the first one can lack a settlement.
    - TS (every reference curve) from 2000-01-14.
    - IN (BVBG.028 instruments) from 2018-01-02.
  - Index compositions are served for the current day only. Index levels go back to 1968 (IBOVESPA).
  - Five ANBIMA datasets are ephemeral: bond rates, ETTJ, VNA, debentures, projections. The debenture link printed on
    ANBIMA's page 404s; the working file is `arqs/dbYYMMDD.txt`. ANBIMA Data needs a login and points to the paid
    Feed for history (OQ-4).
  - COTAHIST `FATCOT` takes 1…10⁶. 1986 prices are in CZ$/CR$. One 2026 line is UTF-8 (ADR-0008).
  - FCA gives tickers only from ~2018. FRE's capital-change tables are gone in 2025.
  - Tesouro Direto history starts 2004-12-31, not 2002.
  - IGP-M index numbers are FGV's and are not in SGS (189 is % only); the only free carrier found is ANBIMA's
    Quadro Indicadores, latest value only.
  - NEFIN moved to `/nefindata/risk-factors/`; its last date was 2026-09-08 on 2026-11-07.
- **Corporate events.**
  - B3's backend is not complete for stock events. It misses ITUB's 10% bonificação of 2025-03 and the 2023 ones of
    SLCE and RADL (OQ-18). It does not list mergers, ticker changes or ISIN changes.
  - PLAN's ARZZ3→AZZA3 case is a ticker and ISIN change on the survivor; SOMA3 is the absorbed company.
  - B3 `BONIFICACAO` factors are percents, `GRUPAMENTO` factors fractions.
  - The ex-date comes from the filing (ITUB 23→26/12/2025; SLCE 30/12/2025→02/01/2026).
  - Equal same-day payouts can be separate installments (GRND3), so never dedupe on (date, value).
- **CDI.**
  - SGS 12 is % a.d. with 6 decimals: SGS 4389 (% a.a.) converted and rounded (5,021 of 5,021 days).
  - BCB's accumulated factors reproduce over [start, end) with the ANBIMA calendar (ADR-0006).
- **PTAX** before 1994 is in the currency of the day (1986, 1989, 1993, 1994 reforms); 9 days have duplicate rows.
- **B3 sessions vs ANBIMA's calendar.** B3 never trades on an ANBIMA non-business day, and skipped 287 ANBIMA business
  days in 2001–2025 (OQ-1).
- **CVM's portal** honours ETag/Last-Modified with 304 and byte ranges. Files are cp1252, `;`-separated. Recent years
  are rewritten; older years are frozen. IPE download links answered an empty HTML shell 4 times in 16 first tries.
- **Fund schema change (CVM 175).** Informe Diário switches to `TP_FUNDO_CLASSE;CNPJ_FUNDO_CLASSE;ID_SUBCLASSE` in
  2023-12.
- **Hosts behind Cloudflare** (B3, CVM, ANBIMA) are fetched at ≤ 1 request/s. B3 and ANBIMA forms are fetched with a
  browser User-Agent.
