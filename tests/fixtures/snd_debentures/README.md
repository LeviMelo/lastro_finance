# snd_debentures fixtures

Real answers of `https://www.debentures.com.br/exploreosnd/consultaadados/` fetched 2026-11-07/08 and read back from
the raw store (Latin-1, CRLF; see `docs/sources/snd_debentures.md`). Byte-exact except where marked "head/sample",
which keeps whole lines of the real file (banner and header included) and drops the other rows.

| file | request | bytes | sha256 |
|---|---|---|---|
| `precos_1993-11.txt` | `mercadosecundario/precosdenegociacao_e.asp?dt_ini=11/01/1993&dt_fim=11/30/1993` (whole) | 813 | `2371aa0a8638c47c0aeb83745ee76e2ce34daef860210477c2b394af64301fe1` |
| `precos_empty_1993-12.txt` | same, 12/01/1993..12/31/1993: "Não existe consulta..." (whole) | 223 | `e62f7263e3a2ba07af0953d837f1aba6e9bbcc59c45b323767bcd0f10688cb57` |
| `precos_2010-03_head.txt` | same, 03/01/2010..03/31/2010: banner, header, first 6 rows (of the 7,395-byte answer; whole answer `3118c95cf1aa0383205975a86c2be418e4e22b32ba66b34b5988790f927e9171`) | 904 | `25e35fcd36b68d4c84ef9552ded639c0c09165f92b9a05a7ff1559e1f297cbc6` |
| `caracteristicas_sample.txt` | `emissoesdedebentures/caracteristicas_e.asp`: banner, header, 7 rows (AAJR11, AALM11, BESC11 x2 co-issuers, ZZDT11, one ISIN `000000000000`, one blank ISIN) of the 6,129,284-byte answer `89d367bff6c1def4ec3dd81f74658994d3a0ccaf1674e4f54f3100c87d743b9c` | 6,334 | `a9bc94e5a8ca7679b120148cdea0c83f70b7db07d4c91d5eeaac62a17f6e7543` |
