# b3_bdi_pdf — B3: Boletim Diário do Mercado (PDF)

**Tier:** P. **Recon date:** 2026-11-09. **Fixtures:** `tests/fixtures/b3_bdi_pdf/` (README has URLs and sha256).
**Decision:** ADR-0034 (streamed; only composition and lending pages kept).

## 1. Access
- `GET https://arquivos.b3.com.br/bdi/download/bdi/<YYYY-MM-DD>/BDI_00_<YYYYMMDD>.pdf`, with a browser
  User-Agent and no login. The English edition is `_en-Us`. Recon of the URL and history is in b3_instruments.md.
- **Served from 2022-03-01 on.** Earlier dates answer HTTP 500.
- **The latest session can lag.** 2026-11-06 (a Friday) still answered 500 on Sunday night, so the daily job
  retries the last 10 sessions.
- **Sizes, measured:**

| Date | Pages | Size |
|---|---|---|
| 2022-06-01 | 420 | 4.0 MB |
| 2023-03-01 | 469 | 4.5 MB |
| 2024-09-02 | 751 | 20.9 MB |
| 2026-11-05 | 1,789 | 32.4 MB |

## 2. Layout of the parsed sections (text extraction, PDFium)
- **Index compositions:**
  - The section title is "Composição das Carteiras de Índices"; in 2026 it is lowercase, after "Indicadores e
    informativos".
  - The period line reads `Para <Mês> a <Mês> de <AAAA>` (the quadrimester). Note (2) gives the session whose
    opening the weights are for.
  - Then, per index: the index name on its own line, then the header `Código Ação Tipo Quantidade teórica
    Participação (%)` (`Código IF …` in 2026), then rows `TICKER NAME TYPE 1.234.567 0,1234`.
  - Until 2024, a footer follows: `Quantidade teórica total: …`, `Valor do Redutor: …`, `Participação total:
    100.00%`. 2026 prints no footer.
  - The rows of every index add up to the printed total on every sample, with one exception: the 2022-09-01
    incoming IGPTW and IFIL, where B3's total differs.
  - 25 to 31 indices are printed. The first session of a quadrimester (2022-09-01) prints both the outgoing and
    the incoming portfolios.
- **Lending, three layouts:**
  - **2022 to mid-2024, "Clearing / Banco de Títulos":** `Ação Empresa Tipo Saldo em número de ações Balanço (R$)`.
    One balance per asset. The balance date is the previous session, given in the page's sentence ("saldo
    acumulado de ações emprestadas em dd/mm/aaaa"). No ISIN.
  - **2024:**
    - open balances `Data Ticker ISIN Empresa ou Fundo Tipo Mercado Saldo em quantidade do ativo Preço Médio
      Saldo em R$`, by market (Neg. Eletrônica D+0, D+1, Registro) plus Total;
    - registered loans `… Mercado Número de Contratos Quantidade de Ativos Valor em R$` with lender and borrower
      rates (min, weighted average, max, % a year).
    - Names and market labels wrap over lines, and "Neg. Eletr / ônica" is split across them.
  - **2026:** the same tables with `Data Código IF Código ISIN Empresa ou fundo …`, and a "Renda Fixa" market for
    fixed-income ETFs.
  - On every 2024 and 2026 sample, each asset's Total equals the sum of its markets.
- **Other content:** prices, derivatives, open interest and corporate actions are not kept (ADR-0034). COTAHIST and
  the Price Report hold the first three.

## 3. Quirks
- **PDFium is not thread-safe.** Concurrent documents crashed the process with exit 127 and no message, so every
  call holds one lock.
- **pypdf is too slow here:** more than 10 minutes on a 751-page file, against 5 s with PDFium.
- Page copies repeat each page's resources uncompressed, so the kept PDF is stored zstd-compressed.

## 4. Backfill (2026-11-09)
- **Coverage.** 1,162 of 1,176 sessions from 2022-03-02 to 2026-11-05 are held: 1.52 GB kept.
- **Not served by B3:** 2022-03-02 → 03-18 (13 sessions) and 2022-12-30. All answer HTTP 500 to curl with a
  browser User-Agent, to the English edition (`_en-Us`), and in the in-app browser. The daily series starts
  2022-03-21. Monthly membership (ADR-0036) is unaffected: it reads the last bulletin of each month.
- **Number conventions vary.** Most bulletins print pt-BR numbers (`4.394.835.131`, `2,5172`); some print en-US
  (`4,394,835,131`, `2.5172`, `8.00%`): 2023-07-19, 2023-12-04, 2025-01 and 2025-02 days, 2026-06-25. One reader
  takes either: the last separator is decimal unless exactly 3 digits follow it.
- **Wrapping.** Narrow columns wrap:
  - the row date ("06/01/202" then "5", seen on 2025-01-06);
  - the market label ("Neg. Elet / rônica" as well as "Eletr / ônica");
  - a long value's last digit ("465.650.070,0 9").

  Each is joined back before parsing.
- **Legacy lending pages carry composition-like rows** ("ULEV34 UNILEVER PLC DRN 1 216,07"), which are not
  compositions. The composition reader skips every lending page. 14,723 such rows had been read as compositions
  before the fix; they were quarantined, and the reparse removed them.
- **No trades table before mid-2023.** The 2022–23 "Banco de Títulos" layout prints balances only, with no
  registered loans.

