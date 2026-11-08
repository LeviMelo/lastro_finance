# anbima_ima fixture (copied byte-exact from raw, fetched 2026-11-07 18:04 UTC)
- `ima_completo.xml` — https://www.anbima.com.br/informacoes/ima/arqs/ima_completo.xml (ref. date 2026-11-06; ISO-8859-1). Hash: `sha256sum *`.
- `ima_sh_20011204.txt`, `ima_sh_20200102.txt`, `ima_sh_20261106.txt` — IMA "Quadro Resumo" per day, `POST https://www.anbima.com.br/informacoes/ima/ima-sh-down.asp` (`Idioma=PT&saida=txt&Dt_Ref=dd/mm/yyyy&Dt_Ref_Ver=20261029`, Referer `ima-sh.asp`, fresh session: no cookies), fetched 2026-11-08, Latin-1, `@`-separated. 2001-12-04 is the first day served; 2020 adds IRF-M 1/1+ and IMA-B 5/5+; 2026 drops IMA-C.
- `ima_sh_no_data_stub.txt` — the answer for 2001-12-03 (no data; HTTP 200, 134 bytes, an out-of-range or non-business day looks the same).
