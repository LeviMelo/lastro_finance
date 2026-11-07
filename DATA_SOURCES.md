# DATA_SOURCES.md

Verified facts about the sources LASTRO reads: **measured, not remembered**. The facts live in one recon note per
source, `docs/sources/<source_id>.md` (template `docs/sources/_TEMPLATE.md`, PLAN §4.13). This file indexes them and
keeps the facts that cut across sources. Where a note disagrees with PLAN.md, a brief or a code comment, the note
wins, and the discrepancy is recorded (ADR-0001). Facts are dated by the recon that measured them; a source can
change without notice.

Registry: `src/fin/reference/sources.toml` (tier, ephemeral, status). `uv run fin status` shows freshness.

## Index

| source | institution | tier | ephemeral | status | note |
|---|---|---|---|---|---|
| `anbima_calendar` | ANBIMA | P | no | parsed | [note](docs/sources/anbima_calendar.md) |
| `anbima_titulos_publicos` | ANBIMA | P | **yes: ~6 business days** | archiving | [note](docs/sources/anbima_titulos_publicos.md) |
| `b3_bdi` | B3 | P | **yes: 21 business days** | archiving | [note](docs/sources/b3_settlement_prices.md) |
| `cvm_cia_cadastro` | CVM | P | **yes: today's snapshot** | archiving | [note](docs/sources/cvm_cia_cadastro.md) |
| `cvm_fi_cadastro` | CVM | P | **yes: today's snapshot** | archiving | [note](docs/sources/cvm_fi_cadastro.md) |
| `b3_reference_rates` | B3 | P | yes, until shown otherwise | recon (location unknown, OQ-5) | [note](docs/sources/b3_reference_rates.md) |
| `b3_cotahist` | B3 | P | no (1986–) | recon | [note](docs/sources/b3_cotahist.md) |
| `bcb_sgs` | BCB | P | no | recon | [note](docs/sources/bcb_sgs.md) |
| `cvm_fca` | CVM | P | no (2010–) | recon | [note](docs/sources/cvm_fca.md) |
| `cvm_fre` | CVM | P | no (2010–) | recon | [note](docs/sources/cvm_fre.md) |
| `cvm_dfp_itr` | CVM | P | no | recon | [note](docs/sources/cvm_dfp_itr.md) |
| `cvm_ipe` | CVM | P | no (2003–) | recon | [note](docs/sources/cvm_ipe.md) |
| `cvm_vlmo` | CVM | P | no (2018–) | recon | [note](docs/sources/cvm_vlmo.md) |
| `cvm_fi_inf_diario` | CVM | P | no (2000–) | recon | [note](docs/sources/cvm_fi_inf_diario.md) |
| `cvm_fi_cda` | CVM | P | no (2005–) | recon | [note](docs/sources/cvm_fi_cda.md) |
| `cvm_fii` | CVM | P | no (2016–) | recon | [note](docs/sources/cvm_fii.md) |
| `cvm_fie` | CVM | P | no (2017–) | recon | [note](docs/sources/cvm_fie.md) |
| `tesouro_transparente` | Tesouro Nacional | P | no | recon | [note](docs/sources/tesouro_transparente.md) |
| `anbima_ettj` | ANBIMA | P | not verified | recon | [note](docs/sources/anbima_ettj.md) |
| `anbima_vna` | ANBIMA | P | not verified | recon | [note](docs/sources/anbima_vna.md) |
| `anbima_projecoes` | ANBIMA | P | not verified | recon | [note](docs/sources/anbima_projecoes.md) |
| `anbima_debentures` | ANBIMA | P | not verified | recon | [note](docs/sources/anbima_debentures.md) |
| `nefin` | NEFIN-FEA/USP | S | not verified | recon | [note](docs/sources/nefin.md) |
| `snd_debentures` | SND | P | not verified | recon | [note](docs/sources/snd_debentures.md) |

## Cross-source facts (2026-11-07)

- **Where PLAN.md §4.4 is wrong or incomplete.**
  - B3's settlement page and TxRef curve page are gone; settlements are in BDI with a 21-day window (ADR-0007).
  - ANBIMA's bond rates are ephemeral, and the file is `msYYMMDD.txt`.
  - COTAHIST's `FATCOT` takes 1, 10, 100, 1,000 and 10,000, and 1986 prices are in CZ$/CR$.
  - FCA gives tickers only from about 2018, one snapshot a year.
  - FRE's capital-change tables thin out in 2023 and are gone in 2025.
- **CDI.**
  - SGS 12 is % a.d. with 6 decimals: SGS 4389 (% a.a., 2 decimals) converted by (1+r)^(1/252)−1 and rounded.
  - It matched on 5,021 of 5,021 days; truncating instead fails on 2,112.
  - BCB's accumulated factors reproduce over [start, end) with the ANBIMA calendar (ADR-0006).
  - SGS daily series accept at most 10-year windows (HTTP 406 beyond).
- **CVM's portal** (dados.cvm.gov.br) honours ETag/Last-Modified with 304 and byte ranges (206). Files are cp1252,
  `;`-separated, CRLF. Recent years are rewritten (weekly cycle observed); older years are frozen.
- **Fund schema change (CVM 175).** Informe Diário switches from `TP_FUNDO;CNPJ_FUNDO` to
  `TP_FUNDO_CLASSE;CNPJ_FUNDO_CLASSE;ID_SUBCLASSE` in 2023-12.
- **Hosts behind Cloudflare** (B3, CVM) are fetched politely at ≤ 1 request/s; B3's need a browser User-Agent.
