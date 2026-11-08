# snd_debentures — SND (debentures.com.br): debenture registry, events, trade statistics

**Tier:** P. **Recon date:** 2026-11-07; parsed 2026-11-08. **Fixtures:** `tests/fixtures/snd_debentures/` (whole small answers; heads of the large ones).

## 1. Access
- Base `https://www.debentures.com.br/exploreosnd/consultaadados/`. IIS, no Cloudflare, no login, generic UA,
  robots.txt 404. A banner says the data is migrating to ANBIMA Data, which needs a login: **continuity risk**.

## 2. Datasets
| dataset_id | URL | content | history |
|---|---|---|---|
| `caracteristicas` | `emissoesdedebentures/caracteristicas_e.asp` | TSV, 85 columns of terms (issuer, CNPJ, ISIN, dates, index, spread, amortisation, Lei 12.431…) for **10,069 debentures, 5,213 of them excluded (dead)** | issues 1981-08 → today; a current snapshot, no versions |
| `agenda` | `eventosfinanceiros/agenda_e.asp` | TSV of interest, amortisation and maturity events | **future only**: past ranges return 0 rows |
| `precos` | `mercadosecundario/precosdenegociacao_e.asp?op_exc=False&dt_ini=&dt_fim=` | TSV of trades per debenture and day: quantity, trades, PU min/avg/max, % of curve PU | 1993-11 → yesterday (sparse before 2010) |

## 3. Quirks
- **`dt_ini` and `dt_fim` are month/day/year.** A first field above 12 is an invalid month: HTTP 500 with a 75-byte
  body (measured 2026-11-07). The output prints dates day/month/year without padding (`3/11/2026`).
- A range with no trade answers 200 with "Não existe consulta para os itens selecionados." Latin-1.
- Since 2012-02-17 the statistics exclude some Cetip electronic trades (page note).
- These are realised trades, not ANBIMA's indicative rates.

## 6. Ephemerality
- Terms and agenda are snapshots: archived daily (terms) and weekly (agenda). Past schedules are rebuilt from the
  terms and from the agendas archived.

## 7. Parsed layout and measurements (2026-11-08)
- **`caracteristicas`** → staging `caracteristicas` (`ingest/snd.py`): Latin-1, CRLF, 2 banner lines + blank, 85 tab-separated
  columns (names padded; `Unidade Monetaria` twice), 10,069 rows for 10,004 codes. One row per code and issuer (9 co-issued
  codes). Zero-padded integers; rates use a comma, except `Percentual Multiplicador/Rentabilidade` and `Amortizacao - Taxa`
  (point). The same snapshot re-sent daily adds no staging rows (ADR-0014). Core: `core/debenture` (ADR-0028).
- **`precos`** → staging `secondary_price` (by year): 713,875 distinct (code, day) rows, 1993-11-01 → 2026-11-05;
  `n_trades` is `-` until 1997 (65 of 67 rows in 1997 still), `% PU da Curva` is `ND` when SND has no curve PU. Overlapping
  request windows re-send identical rows (10,593 repeats): the view `debenture_secondary_price` keeps one per value.
- **Depth:** the first trades are in 1993-11 (5 rows, 2 codes); 1980–1993-10 answer "Não existe consulta" (probed 1985-01,
  1990-01, 1993-01, 1993-10). Multi-year or year-long ranges answer HTTP 500 (measured: 1992, 1980–1993), so the backfill
  walks months (463 held, 42 empty). Two days still answer 500 (2020-12-16, 2021-04-09) and are retried at each backfill.
- **Coverage (core `debenture`, 10,004 codes):** daily PU history (`snd_pu_historico`) 8,955; SND secondary trades 2,871;
  B3 OTC trades (`b3_fixed_income`, 2023-03-13–) 3,101; valid ISIN 9,815; `issuer_id` 5,902.
