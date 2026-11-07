# Fixtures: b3_reference_rates (fetched 2026-11-07 ~09:00-09:40 UTC)
Route 1, "taxas referenciais" backend: `GET https://sistemaswebb3-derivativos.b3.com.br/referenceRatesProxy/Search/GetDownloadFile/<base64 {"language":"pt-br","date":"YYYY-MM-DD","id":"PRE"}>` returns base64 text of a Latin-1 CSV (CRLF).
| file | request | sha256 |
|---|---|---|
| GetDownloadFile_PRE_20261106.b64 / ReferenceRates_PRE_20261106.csv (decoded, 6,973 B, 282 rows) | date 2026-11-06, id PRE | b64 ec2ffde0b36d90a73ea196f520fc15663f152d077f57ca4e9d731fcfa9017077; csv 4e33f9ea8acab2c14029028bce0fc3d39b0980e13d2bf1cd2f72f9a4581d849f |
| GetDownloadFile_DIC_20261106.b64 / ReferenceRates_DIC_20261106.csv | date 2026-11-06, id DIC | b64 8dae0150d6e719d4c54a943c79261ad99d3c64b1de24dfef4ff6531153207ed7; csv a64007b2ab0d1a5fd3560903d9dc0911ca24a8953e03bb6cf57c7d8f20446bcc |
| GetDownloadFile_PRE_20261005.b64 / ReferenceRates_PRE_20261005.csv | date 2026-10-05 (oldest served that day) | b64 40ad37d7a3c3397870780fc0ca3a658c0bdbb52398102e73e0dca1ec932f6fec; csv 9b31a5ab08c399695a4049410e9724f195962cda60cb320756361309760f599e |
Route 2, pesquisapregao `TS{YYMMDD}.ex_` (`GET https://www.b3.com.br/pesquisapregao/download?filelist=TS261106.ex_,`): zip containing `TS261106.ex_` = a PKWARE PKSFX self-extracting EXE (MZ header, ZIP appended at offset 86,036; **never executed**, opened with Python `zipfile`) containing `TaxaSwap.txt`.
| file | cut | sha256 of full originals |
|---|---|---|
| TaxaSwap_20261106_PRE_DIC.txt | the 564 whole lines (CRLF) with code `PRE` or `DIC` from the 31,482-line, 72-char-wide TaxaSwap.txt of 2026-11-06 | `TS261106.ex_` (330,109 B) 209e72eb4196f18c33e81b7532c5251ae1fa57198d89459d5542a6a97fe2bb65; TaxaSwap.txt 0b7695da7ec092d5b6a40117d0a10cc175e2fb4fdfbc4c8376f7674713b3fc83 |
| TaxaSwap_20180102_PRE.txt | 318 `PRE` lines of the 2018-01-02 file (29,033 lines) | `TS180102.ex_` 19afd49855edd5d0c491751022756dc2fba1e9471b00982fd8acb69570aae59c; TaxaSwap.txt 9a4a5521c7afab5c8cdda255040dfcec03ca5ba4d1d41f042a41cfdd8e668630 |
| TaxaSwap_20000114_full.txt | whole TaxaSwap.txt of 2000-01-14, the oldest served date (492 lines of 65 chars) | `TS000114.ex_` bffb87b9e9572e1dc1fd91ff2a0efc2c565fdf3c06e5d2c64cefb15f5c143685; TaxaSwap.txt 161e3f7b81605da73d879f8b9bd10d0e12c14c30c3ddcf454020858451455c99 |
