# anbima_ettj — ANBIMA: Estrutura a Termo das Taxas de Juros Estimada (curva zero)

**Tier:** P. **Recon date:** 2026-11-07. **Fixture:** `tests/fixtures/anbima_ettj/` (txt for 2026-11-06 + the out-of-window stub).

## 1. Access
- Form page `https://www.anbima.com.br/informacoes/est-termo/` (200; "Estão disponíveis ... os últimos 5 dias úteis"; JS alert "Histórico disponível de 5 dias úteis"; hidden `Dt_Ref_Ver=20261029`). Page notice: prices, indices and curves "serão totalmente migradas para o ANBIMA DATA".
- **The window is enforced server-side, not only in JS.** Download: POST `.../est-termo/CZ-down.asp`, fields `escolha=2&Idioma=PT|US&saida=txt|csv|xls|xml&Dt_Ref=dd/mm/yyyy` (Referer set) → `application/download`, `filename=CurvaZero_06112026.txt`. GET with the same query string also works (`CZ-down.asp?Idioma=PT&Dt_Ref=05%2F11%2F2026&saida=csv` → 2,900 B). On-screen: `CZ.asp`.
- Measured (txt, POST): 06/11, 05/11, 29/10/2026 → ~3.2 KB files; **28/10, 01/10/2026, 02/01/2025, 02/01/2020 → 87-byte body** (only the line `0@ANBIMA - …`, identical bytes); GET csv for 30/01/2025 → 200 with 0 bytes. Window = the same 6 business days as the other ANBIMA free files (29/10..06/11).
- Static chart XML: `.../est-termo/xml/CurvaZero_PREF.xml` (311 KB, FusionCharts graph with daily-vertex categories) and `CurvaZero_IPCA.xml` (990 KB) = latest day only; `CurvaZero_PREF_06nov2026.xml` → 200 same size (alias of latest); `_28out2026`, `_23out2026`, `_02jan2025` → 404.

## 2. Datasets
| dataset_id | granularity | history | cadence |
|---|---|---|---|
| curva_zero (txt/csv/xls/xml) | per day: Svensson betas/lambdas (PREFIXADOS, IPCA), vertex table (ETTJ IPCA, PREF, implied inflation), PREF vertices (Circ. 3.361), per-bond errors | **rolling 6 business days** | daily after close (time not verified) |

## 3. Layout (txt, confirmed on fixture; Latin-1, CRLF, 117 lines, `@`-separated, first field = record type)
```
0@Data de Referencia@06/11/2026
1@Grupo@Beta 1@Beta 2@Beta 3@Beta 4@Lambda 1@Lambda 2
1@PREFIXADOS@0,142574760785414@-7,5884442277111E-03@-7,48944729343998E-03@3,89582031522538E-02@1,45258310022224@0,353008109443856
1@IPCA@7,17236579482697E-02@-6,01802381694713E-02@7,33736135708851E-02@1,54871817812221E-02@1,4568116028318@0,29765236105938
2@Vertices@ETTJ IPCA@ETTJ PREF@Inflação Implícita
2@252@6,3470@14,1829@7,3682
3@Vertices@Taxa (%a.a.)      (block "PREFIXADOS (CIRCULAR 3.361)")
4@Titulo@SELIC@Vencimento@Erro (%a.a.)     (block "Erro Título a Título")
4@LTN@100000@01/04/2027@0,0203
```
Record-2 vertices are business days (252, 378, … thousands written `6.804`, `8.316`); rates % a.a.; later rows have empty trailing fields (`2@6.804@7,3980@@`). Betas/lambdas use decimal-comma scientific notation (`E-03`), 12–15 digits.

## 4. Quirks
- Out-of-window requests return **HTTP 200 with a stub body, not 404** → detect by size / missing `Data de Referencia` line.
- Thousands separator `.` only in the vertex column; decimals comma; dates dd/mm/yyyy. xls/csv/xml layouts not examined *(not verified)*.

## 5. Identity fields
Curve = group (PREFIXADOS / IPCA); bond errors keyed by Titulo + SELIC code + Vencimento.

## 6. Ephemerality
**EPHEMERAL (6 business days).** Archive daily (txt via CZ-down.asp, 3 KB). Long-history routes tried: see anbima_titulos_publicos §8 (ANBIMA Data needs a token; Feed is paid). Internet Archive: no systematic daily files; CDX lists `CZ.asp?Dt_Ref=23/10/2026` and `=26/10/2026` captures (Oct 2026), `xml/CurvaZero_PREF.xml` snapshots (2019, 2026-05, 2026-10) and a `CZ-down.asp?...Dt_Ref=30/01/2025&saida=csv` capture of 2026-10-01 (content not fetched; replay was rate-blocked). Own substitute: fit Svensson from B3 DI curves / Tesouro Transparente rates (L4).

## 6b. History routes measured 2026-11-08
- **Month-end 2015-12 → today: SUSEP republishes ANBIMA's English CurvaZero file for each month's last business day**, 131 files archived (`susep_ettj`, docs/sources/susep_ettj.md); equal to our own file on 2026-10-30. This is the only public ETTJ history found.
- No `-sh` ("série histórica") form exists for ETTJ as it does for the IMA: `CZ-sh.asp`, `est-termo-sh.asp`, `CZ-historico.asp` → 404; `CZ.asp` on-screen POST for 2022-09-15 answers a page without a table. pyettj's `get_ettj_anbima` points at the same `CZ.asp`, and works only inside the window.
- ANBIMA Data dataset pages (`data.anbima.com.br/datasets/<slug>`) show a 5-day public sample; their "Download" asks first for name, e-mail, role, company and purpose (a registration form: **not filled**, personal data).

## 7. Open questions
- Publication time; xls/xml/csv layouts; exact 6th-day boundary (`Dt_Ref_Ver` says 20261029).

## 8. Parsed (staging, `ingest/anbima_parsers.py`, 2026-11-07)
Four tables per day, partition `ref_date=`: `parameter` (Svensson beta1-4, lambda1-2, curve PREFIXADOS|IPCA), `vertex` (business days; ETTJ IPCA, ETTJ PREF, implied inflation, % a.a.), `circular_vertex` (Circ. 3.361), `bond_error` (per bond, % a.a.). Units confirmed by golden test: betas are annual rates as fractions, t = du/252, lambdas multiply t (Svensson reproduces PREF/IPCA vertices at 252/504/2520 du to 0.0002 pp). The 87-byte out-of-window stub raises `NotData`. Reparse of the 6 archived days: 12 parameter, 390 vertex, 60 circular, 186 bond-error rows, 0 quarantined.
