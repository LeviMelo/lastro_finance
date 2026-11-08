# b3_fixed_income — B3: renda fixa de balcão do BDI com histórico (`drp.b3.com.br`)

**Tier:** P. **Recon date:** 2026-11-08. **Fixture:** `tests/fixtures/b3_fixed_income/` (Trade pages 1 and 16 of 2024-06-03, SaleOff, Stock; README has sha256).

## 1. Access
- `POST https://drp.b3.com.br/bdi/table/<Table>/<d>/<d>/<page>/<take>`, body `{}`; browser UA (Cloudflare); no auth, no CAPTCHA. Same backend as the BDI of `arquivos.b3.com.br` (b3_instruments.md §7) but **a different, longer window for the fixed-income tables**. `GET /bdi/table/classifications` lists the same 75 tables. `take` ≤ 1000 (1500, 2000, 5000 → HTTP 400).
- `drp.b3.com.br/Web/HistoricoRF` (the page B3 says held the history before 2025-12-11): a React SPA of the UP2DATA app (`src/config.js`: `serverUrl https://drp.b3.com.br/api/`, `useRecaptcha: false`). Its list `GET /api/channels/<channelId>/subchannels/<id>/publications` is public and returns **79 static CSV/ZIP files** (`fileDate` 2025-12-01, last data 2025-12-11) of asset-class aggregates, not trades: `Estoque-<ativo>` (34 files, stock per asset class, e.g. CDB since 2007, LCI 2001, DI 1999, CCB 2001), `Volume-<ativo>` (32), `Outros-<ativo>` (9: DI index since 2008, LF 2010, DEB only 2025-12-11), `Globais-*` (4: negociações definitivas por tipo de ativo **since 1993-01-05** as a zip, compromissadas 2003, total de estoque valorizado since 1994-07). No per-instrument or per-debenture rows. **The download step (`/api/download/request?fileId=…&subChannelId=…&recaptchaToken=`) was not run:** the session's auto-mode classifier refused a request that sends an empty `recaptchaToken` (rule "bot check circumvention"), although the site's own config disables the check. Needs an owner decision before the 79 files (sizes unknown) are fetched; list saved in the run log of 2026-11-08.

## 2. Datasets (measured by one-row probes; bisected to the day)
| table | one row is | first day served on drp | arquivos.b3.com.br |
|---|---|---|---|
| `Trade` (528) | a trade of a registered instrument (DEB, CRA, CRI, CFF, LIG, LF, COE): quantity, PU, volume, rate, venue, time, trade id, ISIN, settlement, status; **~15,000-25,000 trades/day** (16 pages of 1,000 on 2024-06-03, 26 on 2026-11-06) | **2023-03-13** (2023-03-10 empty) | ≥ 2025-01-02, < 2023-01-02 |
| `SaleOff` (531) | settlement volume by instrument type × operation type × method (25-47 rows a day) | 2023-03-01 | same |
| `Stock` (532) | stock/deposited by instrument type (11-42 rows) | 2023-03-01 | same |
| `DebenturesBusiness` (271) | per-instrument day statistics (open/min/max/avg/last, offers, quantity, trades, volume) of **listed** fixed income on Puma: debentures, CRI, CRA, FIDC, RF ETFs (~65 rows) | **rolling M-18**: 2025-05-08 on 2026-11-08, on both hosts | same |
| `ConsolidatedRecords` (529) | per-instrument day statistics (min/avg/max/last PU, trades, volume, ISIN) of all registered OTC instruments | M-18, but **~254,000 rows and 3.7 MB per 1,000 rows (~900 MB a day)**: CCB/CFF dominate; no server-side filter found | same |
| `Register`, `RepurchaseDealings`, `Repodebenture` (compromissadas de debêntures, ~1,065 pages) | | only from 2025-12 (the migration); nothing before | same |
| `DIover` | DI over: operations, volume, average, daily factor, Selic | ≥ 2012-06-04 (not bisected; BCB has the series) | not probed |
| `TDA`, `InstrumentRegistration` | TDA face values monthly; instrument registry (50,000 pages, no history) | | |

## 3. Layout (Trade; identical column names on 2023-06-01, 12-01, 2024-06-03, 2025-01-02, 06-10, 12-10, 2026-01-05, 06-01, 11-06)
`RptDt, DtRef, InstrumentType, Issuer, TckrSymb, Quantity, Price, Vol, Rate, Origin, TradeTime, TradeDate, TradeCode, ISIN, SettlementDt, Situation, IdSer`; dates `YYYY-MM-DDT00:00:00`; `RptDt = DtRef = TradeDate` in every row of both fixtures.
```
DEB RIOMAIS SANEAMENTO BL3 S.A SABP12 54 1041.091772 56218.96 null "Pre-registro - Voice" 16:32:48 #114774180 BRSABPDBS013 2024-06-04 Confirmado
DEB CONCESSIONARIA DAS LINHAS 8 E 9 ... CLTM14 251 981.25 246293.75 7.87 "Pre-registro - Voice" 17:48:09 #114776071 BRCLTMDBS039 2024-06-04 Confirmado
```
Page 1 of 2024-06-03: 887 `Pre-registro - Voice` + 113 `Registro`; `Situation` Confirmado 898, **Ajustado B3 52 (no `TradeCode`)**, Cancelado B3 45, Cancelado 5; `Rate` null in 746 of 1,000 (CRA/CRI trades without a rate); `Price` up to 8 decimals, `Rate` up to 4. Per-table glossaries are PDFs linked in each table's `texts`.

## 4. Quirks
- `Rate` has no unit in the table (magnitudes 6-14 and 112: % a.a. or % of CDI; **not verified against the glossary**).
- Cancelled and adjusted rows stay in the table: they are restatements, kept with their `situation`.
- `lastUpdateDate` of an answer is the table's build time (2024-06-04T09:13 for 2024-06-03): knowledge time comes from the fetch.
- Pages are 1-based; `pageCount` is on every answer. `Stock`/`SaleOff` rows differ by era (Stock grew from 11 to 41 types on 2026-01-05).

## 5. Identity fields
`TckrSymb` (Código IF; debenture ticker or CRA/CRI code), `ISIN` (null for some), `Issuer` (name only, no CNPJ), `IdSer`.

## 6. Ephemerality
`Trade`/`SaleOff`/`Stock`: no `limitDate` and a fixed start (2023-03) on the days probed: not known to roll; the incremental job keeps them current. **`DebenturesBusiness` rolls (M-18): backfill once, then daily (b3_bdi).**

## 7. Archived (2026-11-08)
`ingest/b3_fixed_income.py` (connector `b3_fixed_income`, parser, contracts `fi_trade`, `fi_settlement`, `fi_stock`); the backfill result is in `docs/evaluation/` / the run log. Remaining: the 79 HistoricoRF files (owner decision above); ConsolidatedRecords (volume).
