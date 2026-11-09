## ADR-0034: The daily bulletin PDF is streamed, keeping only its index-composition and lending pages

**Date:** 2026-11-09. **Status:** active. `ingest/b3_bdi_pdf.py`; source note `docs/sources/b3_bdi_pdf.md`.

**Context.**
- B3's daily bulletin PDF (Boletim Diário do Mercado) is the only B3-official history of two series:
  - index compositions (31 indices, theoretical quantity and weight);
  - stock-lending balances and registered loans.
- It is served from 2022-03-01. Each file is 4–32 MB (1,789 pages on 2026-11-05), about 25–37 GB for the whole
  history. The host had 35 GB free.
- Almost all of each file repeats data COTAHIST and the Price Report already hold.
- OQ-20 had set the PDF aside for disk space. The owner overrode that (2026-11-09): stream it, mind RAM as well as
  disk.

**Decision.**
- **Streamed.** Each session's PDF is downloaded, its pages are scanned with PDFium (pypdfium2, Apache/BSD), and
  the following pages are copied into a new PDF:
  - the composition section, any page with the composition table header (`Código [IF] Ação Tipo Quantidade
    teórica Participação (%)`);
  - the lending tables: pages opening with `Data Ticker ISIN` or `Data Código IF Código ISIN`, plus the
    2022–24 "Banco de Títulos" balance.
- **Kept form.** The copied PDF is compressed with zstd level 19 (`.pzst`), because the page copy repeats fonts
  and streams uncompressed (11 MB → 1.4 MB on 2024-09-02).
- **Record.** It keeps the full file's sha256, size, page count, kept page numbers and the reader version
  (ADR-0027 pattern). The rest of the file is dropped.
- **Cost.** Measured: 0.8–1.4 MB kept a day, so ~1.2–1.5 GB for 2022→. Peak RAM is one file per download thread
  (3 threads).
- **Concurrency.** PDFium is not thread-safe: concurrent use crashed the process with no error. All PDFium calls
  hold one lock, so downloads overlap and page work is serial (2–22 s a file).
- **Parsed to staging:**
  - `index_composition`: bulletin, quadrimester, index, asset, theoretical quantity, weight and the session the
    weights are for;
  - `index_total`: printed quantity total and divisor until 2024, with a check that the rows add up to it;
  - `lending_trade`: registered loans by market, with contracts, quantity, value and lender/borrower rate
    min/avg/max;
  - `lending_open`: open balances by market and in total, the short-interest series.

**Consequences.**
- Point-in-time index universes exist from 2022-03. Before that, only the ETF monthly portfolios (2018→) remain.
- The first session of a quadrimester prints the outgoing and the incoming portfolio. Both are kept, keyed by
  `period_start`.
- B3's own inconsistencies stay visible:
  - 2022-09-01, IGPTW and IFIL: the incoming portfolio's printed total does not match its rows
    (`qty_sum_ok = false`);
  - 2026: no totals are printed (`null`).
- Parsing the other tables needs a refetch, because their pages are not kept.
