# ipeadata — IPEA: Ipeadata OData API (FGV IGP index numbers)

**Tier:** S (IPEA republishing FGV). **Recon date:** 2026-11-07.

## 1. Access
- `https://www.ipeadata.gov.br/api/odata4/ValoresSerie(SERCODIGO='<code>')`: 200, no auth, generic UA, a whole series
  in one JSON (`{"value":[{"SERCODIGO","VALDATA","VALVALOR",…}]}`). Metadata: `Metadados('<code>')` (source, unit,
  `SERATUALIZACAO`). `$filter` with `contains()` → 400.

## 2. Datasets
| code | content | range (2026-11-07) |
|---|---|---|
| `IGP12_IGPM12` | IGP-M index number (Aug-1994 = 100) | 1989-06 → 2026-10 (449 rows); last 1243.905 |
| `IGP12_IGPDI12` | IGP-DI index number | 1944-01 → 2026-09 (993 rows); last 1210.686 |
| `IGP12_IGPMG12` | IGP-M % per month | 1989-07 → 2026-10; equals BCB SGS 189 |

## 3. Verification and quirks
- IGP-M Oct-2026 1243.905 equals ANBIMA's Quadro Indicadores. The NTN-C VNA, 1000 × 1243.905 / 183.745 = 6769.735230,
  equals Tesouro's published value (docs/sources/tesouro_vna.md).
- Pre-1994 values are on the chained scale (1989-06: 3.086E-05). No vintages: knowledge time is ours to record.
