# anbima_titulos_publicos — ANBIMA: secondary market of federal bonds (taxas indicativas)

**Tier:** P. **Recon date:** 2026-11-07. **Fixture:** `tests/fixtures/anbima_titulos_publicos/` (all 6 daily txt files served on that day + 1 xls).

## 1. Access
- Free, no auth, generic UA works. Form page `https://www.anbima.com.br/informacoes/merc-sec/` (states "Podem ser consultados os valores referentes aos últimos cinco dias úteis";
  JS alert "Histórico disponível de 5 dias úteis"; hidden `Dt_Ref_Ver=20261029` = earliest date).
- Files: `https://www.anbima.com.br/informacoes/merc-sec/arqs/msYYMMDD.txt` (**YYMMDD**, not DDMMYY — e.g. `ms261106.txt`).
  Spreadsheet `arqs/mYYmonDD.xls` with **pt-BR month** (`m26nov06.xls`, `m26out29.xls`). `arqs/Msec_txt.txt` = latest day (byte-identical to ms261106).
- HTML: `resultados/msec_DDmonYYYY_{ltn,ntn-b,ntn-c,ntn-f,lft}.asp` (pt month, e.g. `msec_29out2026_ltn.asp`), GET works.
- Measured window on 2026-11-07: ms261029…ms261106 = 200 (6 business days; 02/11 holiday); ms261028, 261027, 261023, 261001, 260901, 260102, 250102, 240102, 200102, 160118, 100104 = 404 (IIS 404 page, 1245 bytes). Same for xls and asp of 28/10.
- Page notice dated 2026-03-10: delays in publication due to B3 operational issues.

## 2. Datasets
| dataset_id | granularity | history depth | cadence | URL pattern |
|---|---|---|---|---|
| ms_txt | bond × day | **rolling ~6 business days** | daily (D0 evening, exact time not verified) | `arqs/msYYMMDD.txt` |
| ms_xls | same, Excel | same | daily | `arqs/mYYmonDD.xls` |

## 3. Layout (txt, confirmed on fixture)
- Latin-1, CRLF. Line 1 title, line 2 blank, line 3 header, `@`-separated:
  `Titulo@Data Referencia@Codigo SELIC@Data Base/Emissao@Data Vencimento@Tx. Compra@Tx. Venda@Tx. Indicativas@PU@Desvio padrao@Interv. Ind. Inf. (D0)@Interv. Ind. Sup. (D0)@Interv. Ind. Inf. (D+1)@Interv. Ind. Sup. (D+1)@Criterio`
- Sample: `LTN@20261106@100000@20250110@20270401@13,77@13,7242@13,7549@951,116782@0,00558174106619@13,6004@14,0343@13,5771@14,0069@Calculado`
- Dates YYYYMMDD; decimals comma; rates % a.a. base 252. Layout of the xls *(not verified)*.

## 4. Quirks
- Since 2018-01-18 buy/sell firm average rates replaced min/max (page notice). Retifications are published in place (page lists past corrections) → re-fetch the window daily and keep every sha256 version.

## 5. Identity fields
`Codigo SELIC` + `Data Vencimento` (+ `Titulo`) → Tesouro instrument; ISIN not present.

## 6. Ephemerality
**EPHEMERAL.** Only ~6 business days are served; everything older is 404. Archive daily from now on (fetch whole window each day to catch retifications). Older history: Tesouro Transparente (own rates, not ANBIMA) or paid ANBIMA Data/Feed *(not verified)*.

## 7. Open questions
- Publication time of day; whether ANBIMA Data (data.anbima.com.br) serves free history *(not verified)*.
