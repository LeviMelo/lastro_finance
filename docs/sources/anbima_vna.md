# anbima_vna — ANBIMA: Valor Nominal Atualizado (NTN-B, NTN-C, LFT)

**Tier:** P. **Recon date:** 2026-11-07. **Fixture:** `tests/fixtures/anbima_vna/` (txt for 2026-10-30 + out-of-window stub).

## 1. Access
- Form `https://www.anbima.com.br/informacoes/vna/` (notice: on 2025-09-29 the NTN-C VNA was retified and republished; hidden `Dt_Ref_Ver=20261030`; JS "Histórico disponível de 5 dias úteis"). On-screen `vna.asp` shows the latest day (06/11/2026: NTN-B 4.773,482471 [P], NTN-C 6.779,000823 [P], LFT 20.242,120109).
- Download: POST `.../vna/vna-down.asp`, fields `escolha=2&Idioma=PT&saida=txt|csv|xls|xml&Data=DDMMYYYY&Inicio=dd/mm/yyyy&Dt_Ref_Ver=…` (Referer set) → `filename=VNA_301026.txt`.
- Measured: 06/11, 30/10, 29/10/2026 → 618-byte files; **28/10/2026, 02/01/2025, 02/01/2020 and Saturday 07/11/2026 → 45-byte "Não existem registros para a data solicitada."** Server-side window = 6 business days (29/10..06/11), although `Dt_Ref_Ver` says 30/10.

## 2. Datasets
| dataset_id | granularity | history | cadence |
|---|---|---|---|
| vna | day × {NTN-B, NTN-C, LFT} | **rolling 6 business days** | daily |

## 3. Layout (Latin-1, `;`-separated, 5 header lines then table)
```
Data de Referência :  30/10/2026
Titulo;Código Selic;VNA;Índice;Ref;Válido a partir de
NTN-B;760199;4.771,575461;0,21;P;26/10/2026
NTN-C;770100;6.765,022425;1,47;F;29/10/2026
LFT;210100;20.201,049997;13,65
```
- VNA: thousands `.`, 6 dp decimal comma. `Índice` = monthly % applied (IPCA for NTN-B, IGP-M for NTN-C; LFT row = Selic % a.a.). `Ref` F = closed index, P = projection by ANBIMA's Comitê de Acompanhamento Macroeconômico. The LFT row is ragged (no Ref / Válido columns).
- Footnote: VNA for NTN-B/NTN-C uses the official monthly change truncated to 16 decimals. Methodology PDF `.../informacoes/vna/arqs/vna_metodologia.pdf`; projections methodology `.../vna/metodologia_projecoes.asp` (200).

## 4. Quirks
- NTN-B VNA accrues daily on the projection (29/10 4.771,098828 → 30/10 4.771,575461, same `0,21 P`). Cross-check target for our own VNA from the IPCA index (SIDRA 1737/2266, last = 7695.82).
- Out-of-window: 200 + 45-byte text, not 404.

## 5. Identity fields
`Código Selic` (760199 NTN-B, 770100 NTN-C, 210100 LFT) = bond family, no maturity.

## 6. Ephemerality
**EPHEMERAL (6 business days).** Archive daily. Free history alternative: recompute from the IPCA index (SIDRA) and LFT from Selic (SGS 11/1178), then validate against the archived files. Wayback has only page captures of `/informacoes/vna/` (default.asp, vna.asp, metodologia_projecoes.asp), no data files.

## 7. Open questions
- csv/xls/xml layouts; time of day; any free published VNA before 2026-10 for validating our computation.

## 8. Parsed (staging, `ingest/anbima_parsers.py`, 2026-11-07)
`vna`: day x {NTN-B, NTN-C, LFT}: `vna_brl` (BRL per bond), `index_pct` (% per month for NTN-B/C, % a.a. Selic for LFT), `index_status` F|P, `valid_from` (both null on the ragged LFT row). The 45-byte "Não existem registros" stub raises `NotData`. Reparse: 18 rows (6 days), 0 quarantined.
