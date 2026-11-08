# b3_cotahist — B3: Cotações Históricas (COTAHIST)

**Tier:** P. **Recon date:** 2026-11-07. **Fixture:** `tests/fixtures/b3_cotahist/` (daily 2026-11-06, yearly 2025 and 1986 excerpts).

Measured on the recon date unless marked *(from docs)* or *(not verified)*. Recon was stopped early (usage limit).

## 1. Access
- Plain HTTPS GET, no auth, behind Cloudflare: `https://bvmf.bmfbovespa.com.br/InstDados/SerHist/<NAME>.ZIP`.
  Worked with a browser User-Agent; a non-browser UA was not tried.
- The B3 page `https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/historico/mercado-a-vista/series-historicas/`
  embeds the iframe `https://bvmf.bmfbovespa.com.br/pt-br/cotacoes-historicas/FormSeriesHistoricasArq.asp`, whose JS
  (`/js/SeriesHistoricas.js`) opens `/InstDados/SerHist/<file>`. The form lists every year 1986–2026, only the last 12
  months and only the current year's daily files. Older daily and monthly files are still served when requested directly.
- Layout PDF (rev. 01, 13/04/2017): `https://www.b3.com.br/data/files/C8/F3/08/B4/297BE410F816C9E492D828A8/SeriesHistoricas_Layout.pdf`.
  It is not linked in the page's static HTML (perhaps injected by JS, *not verified*).
- Not checked: terms of use, and the "política comercial" note (FormSeriesHistoricasPrecos.asp) about dates that are not listed.

## 2. Datasets
| dataset | name | history | ZIP size | published |
|---|---|---|---|---|
| yearly | `COTAHIST_AYYYY.ZIP` | 1986–current (1984 and 1985 return 404) | 1986 8.7 MB, 1995 5.3, 2005 8.5, 2015 14.1, 2020 37.2, 2025 89.1 (784 MB unzipped), 2026 YTD 102 | current year rewritten daily (A2026 Last-Modified 2026-11-06 23:33 GMT) |
| monthly | `COTAHIST_MMMYYYY.ZIP` | 01/2014 present; 01/2011–01/2013 return 404 (not bisected) | 1.1–10 MB | at month end (M102026 2026-10-30 23:48 GMT) |
| daily | `COTAHIST_DDDMMYYYY.ZIP` | 02/01/2014 present; 02/01/2013 returns 404 (not bisected) | 47 KB (2014) – 470 KB (2026) | same evening, ~23:30 GMT (D06112026 23:25 GMT) |

The form names the 1986–2007 zips in lowercase `.zip`; the server is case-insensitive (`.ZIP` worked).
Zip member names vary: `COTAHIST.A1986` (no extension), `COTAHIST_A2025.TXT`, `COTAHIST_D06112026.TXT`.

## 3. Layout
Positions are from the PDF, 1-based and inclusive. All three files measured have every line at 245 bytes + CRLF.
- Header `00`: 1-2 "00"; 3-15 "COTAHIST.AAAA"; 16-23 "BOVESPA "; 24-31 generation date AAAAMMDD; 32-245 blanks.
- Trailer `99`: 1-31 as in the header; 32-42 N(11) total records; 43-245 blanks.

| field | pos | type | field | pos | type |
|---|---|---|---|---|---|
| TIPREG "01" | 1-2 | N(2) | PREOFV | 135-147 | (11)V99 |
| DATPRE | 3-10 | AAAAMMDD | TOTNEG | 148-152 | N(5) |
| CODBDI | 11-12 | X(2) | QUATOT | 153-170 | N(18) |
| CODNEG | 13-24 | X(12) | VOLTOT | 171-188 | (16)V99 |
| TPMERC | 25-27 | N(3) | PREEXE | 189-201 | (11)V99 |
| NOMRES | 28-39 | X(12) | INDOPC | 202 | N(1) |
| ESPECI | 40-49 | X(10) | DATVEN | 203-210 | AAAAMMDD |
| PRAZOT | 50-52 | X(3) | FATCOT | 211-217 | N(7) |
| MODREF | 53-56 | X(4) | PTOEXE | 218-230 | (07)V06 |
| PREABE / PREMAX / PREMIN / PREMED / PREULT / PREOFC | 57-69 / 70-82 / 83-95 / 96-108 / 109-121 / 122-134 | (11)V99 | CODISI | 231-242 | X(12) |
| | | | DISMES | 243-245 | 9(3) |

Code tables in the PDF:
- TPMERC: 010 vista; 012/013 exercício de opções de compra/venda; 017 leilão; 020 fracionário; 030 termo; 050/060 futuro; 070/080 opções de compra/venda.
- INDOPC: 1 US$; 2 TJLP; 8 IGPM; 9 URV.
- CODBDI and ESPECI have their own tables in the PDF.

What was confirmed: the record length, the header and trailer parse, and plausible value distributions per field
(TPMERC, CODBDI, FATCOT, MODREF, dates). The fields were not checked against an independently known quote *(not verified)*.

## 4. Quirks (measured)
- **PREMED is not bounded by high/low.** It lies outside [PREMIN, PREMAX] on 6,520 standard-lot sessions: 1989-91,
  and from 2021 about 500 a year, mostly BDRs. So it includes trades the high/low do not. O/H/L/C are consistent on
  every session but one: BGIP4 2021-05-18 has 1 trade of R$ 2,224.00 and every price 0 (quality finding, ADR-0022).
- Encoding: the 2025 and daily files are ASCII only. The 1986 file has one 0xD0 byte and 25 rows with PRAZOT = `\x00\x0f ` (binary garbage). Decode as latin-1 and never fail on a byte.
- **The trailer count changed meaning.** In 1986 the trailer equals records + 2 (header and trailer included, as the PDF says). In the 2025 yearly and 2026 daily files it equals the data records only.
- **FATCOT is not only 1 or 1000.**
  - 1986: 1000 (154,395 rows) and 1 (23,586).
  - 2025: 1, 100 (28,088), 1000 (1,149), 10000 (86) and 10 (3).
  - Daily 2026-11-06: 1, 100 and 1000.
- MODREF: 1986 has `CZ$ ` and `CR$ `; 2025 has `R$  `. Prices are in the currency of the day, so a currency-reform table is needed.
- Codes missing from the 2017 PDF tables: TPMERC 021 (2025 and the daily file); CODBDI 13/34/35/36/92/93 (2025). CODBDI 12 (FII) is in the PDF.
- PRAZOT is zero-padded (`000`) in the daily file but space-padded (`  0`, ` 30`) in the 2025 yearly file. It is blank for some non-termo rows.
- CODISI is never blank in the three files. In 1986 it holds B3 internal codes; the PDF says ISIN is used from 15-05-1995 *(from docs)*.
- The 1986 header generation date is 19991210, so old years are re-generated files.

### Measured on the full history (2026-11-07, parser `fin/ingest/b3_cotahist.py`)
- **Rows.** 1986–2025 yearly files: 21,394,322 records; every line was 245 bytes; every trailer matched (n or n+2).
- **FATCOT.** Also takes **100000** (2005, 49 rows) and **1000000** (2016–2017, 28 rows), and **0** (2007, 4 rows,
  quarantined). The rule accepts the powers of ten 1…10⁶.
- **Out-of-range opens/closes.** 1,237 rows have an open or close outside [low, high] (most in 2005 and 2020;
  e.g. `MVI 2` 1986-05-06: open 1199.99 > high 1199.90). 2 rows have low > high. They are quarantined, not dropped.
- **Sessions vs the ANBIMA calendar** (2001-01-01…2025-12-31). B3 traded on no day ANBIMA calls a holiday or
  weekend, but did not trade on 287 ANBIMA business days:
  - 24/12 and 31/12 (18 each);
  - 09/07 (16) and 25/01 (15): São Paulo state and city holidays;
  - 20/11 (11) before it became national;
  - some last business days of the year;
  - 2014-06-12 (World Cup opening).

  So B3's calendar is observed from COTAHIST sessions, not derived from ANBIMA's (OQ-1).
- **Cross-check against B3's TradeInformationConsolidated (2026-11-06).**
  - BOVA11 and HGLG11 agree on low, high, last, trades, quantity and volume, exactly.
  - PETR4 agrees on prices and trades (70,037) but not on quantity: 48,069,700 there vs 47,669,700 here. Volume is
    R$ 2,182,862,133 there vs R$ 2,164,746,133 here.
  - PETR4F (199,437) and PETR4T (206,200) do not explain the 400,000-share gap (OQ-17).

## 5. Identity fields
- CODNEG → TICKER, valid at DATPRE.
- CODISI → ISIN; before 1995-05-15 it holds an internal code.
- DISMES → distribution number.
- NOMRES is the issuer's short name, not an identifier.

## 6. Ephemerality
Low. Yearly files back to 1986 are still served, and daily files back to 2014. Old years can be re-generated (1986 was in 1999), so store the sha256 of each download.

## 7. Open questions
- The exact first available daily and monthly date (between 2013-01 and 2014-01).
- The meaning of TPMERC 021 and CODBDI 13/34/35/36/92/93 (a newer B3 document?).
- When the trailer-count convention changed, and when FATCOT 10/100/10000 started.
- A field-level price check against an independent quote, and a PREEXE/PTOEXE check on an option row.
- The terms of use, and behaviour with a non-browser User-Agent.
