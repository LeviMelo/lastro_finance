# b3_fundosnet — B3 Fundos.NET: structured distribution notices of FIIs and Fiagros

**Tier:** P (B3's public filing system; the JSON endpoint is undocumented). **Recon date:** 2026-11-07.

## 1. Access
- Listing: `GET https://fnet.bmfbovespa.com.br/fnet/publico/pesquisarGerenciadorDocumentosDados?d=0&s=<offset>&l=200
  &o[0][dataEntrega]=desc&idCategoriaDocumento=14&idTipoDocumento=41` → JSON `{data, recordsFiltered, recordsTotal}`.
  Browser UA, no login or cookie. `l` = 500 → 302 (cap between 200 and 500); no category filter → 0 rows. robots.txt
  404.
- Document: `GET .../downloadDocumento?id=<id>` → XML (~1 KB).

## 2. Content
- 36,584 notices "Aviso aos Cotistas – Estruturado / Rendimentos e Amortizações", **2016-11-30 → today** (ids from
  6959). Nothing before 2016, the system's start. Other categories exist (Fato Relevante 15,819 from 2016-04; Informe
  Mensal 702,422 from 2016-06) and are not archived.
- Listing row: id, `dataEntrega` (dd/mm/yyyy hh:mm, **knowledge time to the minute**), dataReferencia, fund,
  `nomePregao`, versao, status.
- XML: `DadosGerais` (NomeFundo, CNPJFundo, CodISINCota, CodNegociacaoCota…) and `InformeRendimentos/Provento`
  (CodISIN, CodNegociacao, `Rendimento` {DataBase = data-com, ValorProvento per unit, DataPagamento,
  PeriodoReferencia, RendimentoIsentoIR}, `Amortizacao`).
- Example: TINF11, 0.40 per unit, data-com 2026-11-06, paid 2026-11-13, delivered 2026-11-06 18:08.

## 3. Ephemerality and cost
- Not ephemeral. The full history is 183 listing pages + 36,584 documents. Sequentially at 1 request/s it ran at
  about 0.5 notices/s (≈ 20 h; the server answers in 1-2 s). With 8 downloads in flight (ADR-0023) the last 1,210
  notices took 2 minutes after the listing walk. A day adds a few dozen.

## Parsed (2026-11-07, `ingest/fundosnet.py`; first 16,685 notices of the backfill)
- **Two layouts** (all 36,384 notices surveyed 2026-11-08):
  - from 2022: one `<Provento>` per class, with its own `CodISIN`/`CodNegociacao` and `ValorProvento` (20,415 notices);
  - before: `Rendimento`/`Amortizacao` directly under `InformeRendimentos`, the ISIN in `DadosGerais`
    (`CodISINCota`) and the value in `ValorProventoCota`, plus `DataAprovacao` (15,969 notices).
  - The first parser read only the first layout, so 2016-2021 was missing. Both now give 40,790 rows; an empty
    `<Rendimento/>` declares nothing.
- Dates are ISO. Values are plain decimals with up to 19 decimals (one notice) and 7 integer digits, stored as
  `Decimal(38,22)`. More decimals are refused, since a cast would round.
- 19,299 Proventos: 18,514 Rendimento, 1,215 Amortizacao (1,093 Parcial, 122 Total); 430 carry both. Income tax
  flag: Sim 18,243, Não 271.
- Quarantined by rule: 2 negative values (RENV11 −0.07, WSEC11 −0.075, 2024-10); 9 payments dated before the
  data-com, one with data-com typed 2029-09-29 (YUFI11, payment 2023-10-16). 41 Proventos have no
  `CodNegociacao` (unlisted quotas); kept with a null ticker.
- One notice (id 991793) holds an `InformeMensal`: counted as not data.
- Listing: 1.7 % of documents are re-filings (`versao` 2–5); `dataEntrega` is minute-precise Brasília time.
- Personal contact fields (`ResponsavelInformacao`, `TelefoneContato`) are not parsed.
- **Source errors kept, not quarantined (2026-11-08).**
  - 27 notices write the CNPJ formatted (`17.007.443/0001-07`): it is normalized to 14 digits.
  - 108 rows carry a malformed ISIN (`0`, `-`, `RBR PLUS`, `TGARCTF009` without `BR`). The payout is kept as written,
    and core matches it through the trading code valid at the data-com.
  - 214 rows have a payment date before the data-com (a year typo: base 2020-12-30, paid 2020-01-15). Kept as
    written; adjustment uses only the data-com and the value.
  - Both cases are listed by the quality check `fii_payout_suspect`.
