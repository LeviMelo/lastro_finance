# tax_rules — Brazilian legal texts behind `src/fin/tax/rules.toml`

**Tier:** P (official texts). **Read:** 2026-11-09. Planalto pages were fetched with a browser User-Agent (HTTP
200). IN RFB 1585/2015 is rendered by JavaScript, so it was read in the in-app browser (multivigente view,
`normasinternet2.receita.fazenda.gov.br/#/consulta/externa/67494`). Used by ADR-0033.

| Rule (code) | Text read | URL |
|---|---|---|
| swing 15 %, day trade 20 %, IRRF 0.005 % with the R$ 1 dispense, R$ 20,000 stock exemption, regressive fixed-income table | Lei 11.033/2004 arts. 1-3; marked "Vide MP 1.303/2025 … vigência encerrada" (the MP lapsed) | planalto.gov.br/ccivil_03/_ato2004-2006/2004/lei/l11033.htm |
| FII/Fiagro exemption conditions (≥ 100 holders, holder < 10 %, Lei 14.754/2023 wording) | Lei 11.033/2004 art. 3 III and §1 | same |
| rates 15/20 %, exemption excludes day trade and equity ETFs, average cost, bonus cost, split cost, IRRF offsets, loss pools, day-trade pairing and 1 % IRRF | IN RFB 1585/2015 arts. 24-28, 56-65 | normas.receita.fazenda.gov.br/sijut2consulta/link.action?idAto=67494 |
| FII 20 %, Fiagro 20 % | Lei 8.668/1993 art. 18 (Lei 9.779/1999), art. 20-D (Lei 14.130/2021) | planalto.gov.br/ccivil_03/leis/l8668.htm |
| JCP 15 % to 2025-12-31, 17.5 % from 2026-01-01 | Lei 9.249/1995 art. 9 §2; LC 224/2025 art. 8 and art. 14 III | planalto.gov.br/ccivil_03/leis/l9249.htm, …/leis/lcp/lcp224.htm |
| dividends: 10 % when one payer's month exceeds R$ 50,000, from 2026; outside it, results to 2025 approved by 2025-12-31 | Lei 15.270/2025 art. 2 (new art. 6-A of Lei 9.250), art. 8 | planalto.gov.br/ccivil_03/_ato2023-2026/2025/lei/L15270.htm |
| fixed-income ETFs 25/20/15 % by average repricing term, at source, from 2015-01-01 | Lei 13.043/2014 art. 2, art. 113 II | planalto.gov.br/ccivil_03/_ato2011-2014/2014/lei/l13043.htm |
| IOF 96 % → 0 % over days 1-30 | Decreto 6.306/2007 art. 32 and Anexo | planalto.gov.br/ccivil_03/_ato2007-2010/2007/decreto/d6306.htm |
| DARF below R$ 10 carried | Lei 9.430/1996 art. 68 §1 | planalto.gov.br/ccivil_03/leis/l9430.htm |
| DARF code 6015; due on the last business day of the next month; worked example (gain 9,967.00 → DARF 1,492.05) | Receita Federal, "Cálculo e Pagamento do Imposto" (updated 2025-11-19) | gov.br/receitafederal/pt-br/assuntos/meu-imposto-de-renda/pagamento/renda-variavel/bolsa-de-valores-1/calculo-e-pagamento-do-imposto |

**Not read (open):**
- a Receita ruling on units and the exemption;
- the tax treatment of crypto ETFs and ETF-FII quotas;
- come-cotas;
- Lei 14.754/2023 (offshore);
- the annual minimum tax of Lei 15.270 (art. 16-A).
