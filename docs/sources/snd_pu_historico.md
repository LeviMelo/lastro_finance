# snd_pu_historico — SND (debentures.com.br): PU Histórico of every debenture

**Tier:** P. **Recon date:** 2026-11-08. **Fixture:** `tests/fixtures/snd_pu_historico/` (ZZDT21 dead, SABP12 registered, VALE23 header-only; README has sha256).

## 1. Access
- `GET https://www.debentures.com.br/exploreosnd/consultaadados/emissoesdedebentures/puhistorico_e.asp?op_exc=False&ativo=<ticker>&dt_ini=<dd/mm/yyyy>&dt_fim=<dd/mm/yyyy>`; no login, generic UA, IIS. Found through the `formpu` form of the site's home page (`puhistorico_r.asp`; the `_f` page lists 4,855 registered debentures; `op_exc` True/False/Nada changes only that list: the export answers identically).
- **Dates are day first here** (`precosdenegociacao` of the same site reads month first, snd_debentures.md §3). An invalid date (e.g. 12/31/2024) is HTTP 500; empty dates give the header only.
- Measured: a full range (01/01/1980 → today) of one debenture is 47-62 KB (640-850 rows) and takes ~2.3 s; a dead debenture (AALM11, ZZDT21) is served as well as a live one; a ticker the SND has no PU for (VALE23) answers 200 with the 138-byte header.
- The site banner says its data is migrating to ANBIMA Data (login/reCAPTCHA, see anbima_debentures.md): continuity risk, so the whole history is fetched once now.

## 2. Datasets
| dataset_id | granularity | history | cadence |
|---|---|---|---|
| `pu` | debenture × business day: Valor Nominal, Juros, Prêmio, Preço Unitário, Critério, Situação | from the debenture's issue (first rows of SABP12 2022; whole life, dead ones included) | daily; refreshed weekly/monthly by `--mode incremental` (last 60 days of each registered debenture) |

## 3. Layout (Latin-1, CRLF, tab-separated, trailing tab; newest first)
```
PU Histórico - Gerado em 08/11/2026 01:40:34
<blank>
Data do PU	Ativo	Valor Nominal	Juros	Prêmio	Preço Unitário	Critério de Cálculo	Situação
31/12/2024	SABP12	1.052,678070	82,855032	-	1.135,533102	Padrão - SND	Reg.
```
Footer after two blank lines: "Valores expressos em reais." and a disclaimer ("os valores refletem a nossa interpretação da escritura"). `-` (also `-  `) is no value; thousands dot, decimal comma, six decimals.

## 4. Quirks
- The PU is SND's reading of the deed (par value + accrued remuneration), **not a traded price**; "Prêmio" is a premium paid on the date and is not in the PU (AALM11 2024-11-08: PU = Valor Nominal, Prêmio 13.01).
- The header line carries the generation time: every re-fetch is a new raw object (stored as a delta), staging keeps only changed rows (`dedup_staging`).
- `Situação` is per row (`Reg.`, `Exc.`).

## 5. Identity fields
`Ativo` = debenture ticker (same code as ANBIMA's `Código` and SND's `caracteristicas`); the register of tickers is the archived `snd_debentures/caracteristicas` (10,073 rows, dead included).

## 6. Ephemerality
Not ephemeral (full history served per request) but at continuity risk (ANBIMA Data migration). Complements `anbima_debentures` (indicative rates, 6-day window) and B3 `Trade` (traded PU, since 2023-03): with the par-value path from here, a traded PU becomes a % of PU curve.

## 7. Archived
`ingest/snd_pu.py` (connector `snd_pu_historico`, contract `debenture_pu`); counts in the run log and STATUS.
