# b3_cotahist fixtures

Fetched 2026-11-07 ~08:27 UTC. Cut: header line, then (in file order) the first N records of each (TPMERC, FATCOT)
pair, then the trailer line. Whole lines, original bytes (latin-1/ASCII, CRLF, 245 chars + CRLF). The trailer count is
the original file's count, so it does not match the excerpt length.

| file | source URL | N | sha256 of full original ZIP |
|---|---|---|---|
| COTAHIST_D06112026_excerpt.TXT | https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_D06112026.ZIP | 25 | 7470234170bf376c4ff0ce9f30a338bd55a98e5a82bf8c7cedeefcfd5f7f323d |
| COTAHIST_A2025_excerpt.TXT | https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A2025.ZIP | 12 | 6cc0ad851c8f605ca30418acac48be81f1767f6ed05b4f563772d06ae448047d |
| COTAHIST_A1986_excerpt.TXT (FATCOT 1000, MODREF CZ$/CR$) | https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A1986.ZIP | 15 | 350e6086c8f991484832ca3cd23e900b692769bfd3311017800231fd896c8018 |

Layout PDF (not committed): https://www.b3.com.br/data/files/C8/F3/08/B4/297BE410F816C9E492D828A8/SeriesHistoricas_Layout.pdf
(rev. 01, 13/04/2017; sha256 fc4f35066ddd8e1a359f5f3f1e2318b8faec9f3b3075216636d6811dd10e7dfd).
