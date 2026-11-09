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
