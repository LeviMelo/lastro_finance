## ADR-0029: ETF NAV comes from Fundos.NET, linked to the quota by trading name and checked by price

**Date:** 2026-11-08. **Status:** active. `ingest/fundosnet_daily.py`, `ingest/fundosnet_cda.py`, views
`etf_daily`, `etf_nav`, `etf_link` (`catalog.py`), check `etf_link`, dossier ETF table.

**Context.** ETFs are CVM type FIIM. CVM's open-data INF_DIARIO holds them only until 2018-09: BOVA11's last row is
2018-09-06, and 202610 has 0 FIIM rows. Since then they report to B3's Fundos.NET, which holds 225,340 daily
reports from 2018-06-29 and 8,128 monthly portfolios (docs/sources/b3_fundosnet_daily.md, b3_fundosnet_cda.md).
Neither source carries a ticker or ISIN: the report names the fund by CNPJ, and its listing row shows the B3 trading
name. B3's instruments file carries no CNPJ, and CVM's CDA lists ETF holdings by CNPJ only. Fixed-income ETFs
(IMAB11, FIXA11, B5P211, LFTS11…; segment FIXED INCOME, T1) are absent from COTAHIST; they appear only in the Price
Report, archived from 2026-10-19 (OQ-20).

**Decision.**
- NAV per quota is Fundos.NET's daily report from 2018. Before that it is CVM's INF_DIARIO rows of FIIM funds (21
  funds 2004–2018; the CVM register keeps cancelled funds, so dead ETFs are included). `etf_nav` keeps one row per
  fund and date: Fundos.NET's latest delivered version, whose delivery minute is the knowledge time.
- The ETF → quota link joins the listing's trading name to COTAHIST's NOMRES (CODBDI 14); BOVA11 is "ISHARES BOVA"
  on both. A link values nothing until the median of close / NAV over common days is within 10 % of 1 (`verified`).
  Crypto and foreign ETFs sit 2–5 % off (NAV struck at another hour); a wrong ticker would be far off. Unverified
  links are `etf_link` findings.
- A fixed-income ETF without COTAHIST prices is shown at its NAV.

**Alternatives.**
- B3's listed-funds pages (CNPJ and ticker together): they answered 500/403 to curl and were not pursued while
  FNET suffices.
- Matching by issuer name to B3's `CrpnNm`: rejected; CVM and B3 spell the names differently ("CLASSE DE ÍNDICE"
  vs "FUNDO DE ÍNDICE").
- Issuer websites (iNAV): tier U, not used.

**Would overturn it.** A free official CNPJ ↔ ISIN table for fund quotas, or B3 changing trading names so that
they no longer equal NOMRES.
