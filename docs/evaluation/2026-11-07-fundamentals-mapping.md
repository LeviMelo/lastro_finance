# Fundamentals: 15 standard metrics mapped by account name across the industrial and bank templates; 441-458 companies per metric for DFP 2024 (2026-11-07)

Regime: view `fundamental_metric` (`fin/catalog.py`) over `fundamental_fact` (ADR-0017).

**Method.** Fixed CVM accounts (`ST_CONTA_FIXA = S`), current period (`ÚLTIMO`). A metric is defined by statement
and account name; the shallowest code wins. Account codes differ by template while names do not:
- ~500 issuers use the industrial template;
- 16 + 10 banks use two financial templates.

| metric | industrial (DFP 2022–2025, modal) | banks |
|---|---|---|
| equity | BPP 2.03 "Patrimônio Líquido Consolidado" | 2.07 (16), 2.08 (10) |
| net income | DRE 3.11 "Lucro/Prejuízo Consolidado do Período" | 3.11 "Lucro ou Prejuízo Líquido Consolidado do Período" (16), 3.09 (10) |
| revenue | DRE 3.01 "Receita de Venda de Bens e/ou Serviços" | 3.01 "Receitas (da/de) Intermediação Financeira" |
| EBIT | DRE 3.05 "Resultado Antes do Resultado Financeiro e dos Tributos" | not in the template |

**Coverage, DFP 2024 consolidated.** Total assets, equity, revenue, net income, gross profit, pre-tax income, cash and
the three cash flows: 456–458 companies each. EBIT and current/non-current items: 441 (the banks have none).
Equity attributable to controlling shareholders is a fixed account only in the bank templates (10).

**Spot values (R$ bn, 2024).**
- Petrobras: revenue 490.8, total assets 1,124.8, pre-tax income 54.7.
- Vale: revenue 206.0, total assets 496.3.
- Itaú: total assets 2,854.5, pre-tax income 47.6.

Itaú's assets match the source note's reading of the raw file (`cvm_dfp_itr.md` §3).

**Insurers (checked the same day).** IRB, Porto Seguro, Caixa Seguridade and Wiz use the same fixed account names, so
the mapping covers them. The one exception was IRB's operating cash flow, which is now mapped: "Caixa Líquido
Atividades Seguradora/Resseguradora", 2 companies. A 16th metric, `noncontrolling_interest`, serves book value
(ADR-0021).
