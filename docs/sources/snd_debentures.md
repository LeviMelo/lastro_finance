# snd_debentures — SND (debentures.com.br): debenture registry, events, trade statistics

**Tier:** P. **Recon date:** 2026-11-07. **Fixture:** none yet (the exports are 0.5–9 MB).

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
