# b3_reference_rates — B3: taxas referenciais

**Tier:** P. **Recon date:** 2026-11-07 (barely started; stopped early). **Fixture:** none yet.

## 1. Access
- `https://www2.bmf.com.br/pages/portal/bmfbovespa/boletim1/TxRef1.asp?Data=06/11/2026&Data1=20261106&slcTaxa=PRE` → **404** with browser UA and without UA; `http://` → 520; `https://www2.bmf.com.br/` → 403. Same host's ajustes page now 301-redirects to the BDI (see b3_settlement_prices.md), so the old pages are probably decommissioned (B3 notice of 31/03/2026).
- BDI catalog (`arquivos.b3.com.br/bdi/table/classifications`) has no "taxas referenciais" table by name. Candidates *(not verified)*: `EconomicIndicators` (hasHistory, D-21), BVBG files in `www.b3.com.br/pesquisapregao/download?filelist=…` (e.g. TS/TR codes), the BDI PDF.

## 6. Ephemerality
Unknown. If only BDI-style D-21 is available, archive daily.

## 7. Open questions
- Current location of PRE/DIC curves; slcTaxa code list; layout; history depth. All not verified.
