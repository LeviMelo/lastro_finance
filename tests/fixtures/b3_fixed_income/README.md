# b3_fixed_income fixtures

Byte-exact answers of `POST https://drp.b3.com.br/bdi/table/<Table>/2024-06-03/2024-06-03/<page>/1000`, body `{}`,
fetched 2026-11-08 (see `docs/sources/b3_fixed_income.md`).

| file | request | bytes | sha256 |
|---|---|---|---|
| `trade_20240603_p1.json` | Trade, page 1 of 16 (1,000 trades) | 278,190 | `377c973c28d04a60a83c48e6e6aa4f0042f41572b10f27744f4e5e45aa867d7d` |
| `trade_20240603_p16.json` | Trade, page 16 of 16 (284 trades) | 97,715 | `ec27f63efdcd63b2a8a7e77d9437ddba2a531e72a6632604b99d673317ab4ab2` |
| `saleoff_20240603.json` | SaleOff, page 1 of 1 (33 rows) | 9,126 | `49f2a3946812c975064f4a09d4c36902196b2d4527467c4ec163a0ee79c8b7fe` |
| `stock_20240603.json` | Stock, page 1 of 1 (11 rows) | 6,134 | `dc80658bb8d382cee38d484025fcf7282263de9a23b163b720d4af2e2c438661` |
