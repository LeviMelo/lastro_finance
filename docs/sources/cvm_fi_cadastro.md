# cvm_fi_cadastro — CVM: cadastro de fundos / registro fundo-classe-subclasse (FI/CAD)

**Tier:** P. **Recon date:** 2026-11-07 (partial; stopped by usage limit). **Fixture:** none yet.

Every statement below was measured on the recon date against a real response, unless marked *(from docs)* or
*(not verified)*. Only listings and HTTP headers were read.

## 1. Access
- Same CVM tree and header behaviour as `cvm_fi_inf_diario.md` §1 (ETag/Last-Modified, 304 on conditional GET, Range 206, Cloudflare 4 h cache).

## 2. Datasets
| dataset_id | granularity | history depth | cadence | publication lag | URL pattern |
|---|---|---|---|---|---|
| cad_fi (legacy) | fund | snapshot | daily (LM 07-Nov-2026 04:22 GMT) | — | `FI/CAD/DADOS/cad_fi.csv` (17.9 MB) |
| cad_fi_hist | fund attribute history | *(not verified)* | daily | — | `FI/CAD/DADOS/cad_fi_hist.zip` (18.7 MB) |
| registro_fundo_classe | fund / class / subclass | snapshot | daily | — | `FI/CAD/DADOS/registro_fundo_classe.zip` (6.9 MB; members *(not verified)*) |
| layouts | — | — | — | — | `FI/CAD/META/meta_cad_fi.txt`, `meta_cad_fi.zip`, `meta_registro_fundo_classe.zip` (not read) |

## 3–5. Layout, quirks, identity
- Not read *(not verified)*. Golden CVM-175 fund not chosen yet.

## 6. Ephemerality
- `cad_fi.csv` and `registro_fundo_classe.zip` are single overwritten files with no dated copies → **ephemeral snapshots: archive daily** (cheap with ETag/304). Whether `cad_fi_hist` covers all attribute history *(not verified)*.

## 7. Open questions
- Members and columns; fund↔class↔subclass keys; is cad_fi still maintained for adapted funds; golden fund trace old→new.
