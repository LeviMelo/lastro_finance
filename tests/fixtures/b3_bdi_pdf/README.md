# b3_bdi_pdf fixtures

Page subsets of three real bulletins, fetched 2026-11-09 from
`https://arquivos.b3.com.br/bdi/download/bdi/<YYYY-MM-DD>/BDI_00_<YYYYMMDD>.pdf` (browser User-Agent, no login).

Each fixture is the listed pages, copied with pypdfium2 5.15.1 (`import_pages`) and compressed with zstd level 19.
That is how the connector keeps a bulletin, cut further to stay under 1 MB.

| fixture | original bytes | original sha256 | pages kept | fixture sha256 |
|---|---|---|---|---|
| `BDI_00_20220901.subset.pdf.zst` | 4,648,146 | `747199f486acfb5ee8b0d2a121afd1b9709df8e20d69910b52cd036895b9e072` | 22, 23, 24, 66, 67, 105, 106, 479, 490 | `4a07dfa2187f65181ed100acae4db1162152aeb12b724e6876e0a2d4a19c883a` |
| `BDI_00_20240902.subset.pdf.zst` | 20,922,928 | `84275b5d3f75c9b69f20eedf3dd206cd652e0586b6eb3395d22cbe6657a7312d` | 23, 24, 25, 63, 64, 685, 730, 731, 751 | `5e46be906fdb2a0f293d8b53c1a045b042dd94efbd9f8fc95aa4644d6100988d` |
| `BDI_00_20261105.subset.pdf.zst` | 32,353,796 | `c07504fde663d30d0bfbee5555667fb613e1aa6094d9254781884b1e1df97c24` | 1036, 1037, 1038, 1063, 1064, 1716, 1758, 1759, 1788 | `225fa02537a484a82da307142752a20b52269b9c278a9eb13afa81af292e1483` |

What each one covers:
- **2022-09-01:** the outgoing (May–Aug) and incoming (Sep–Dec) portfolios printed on one session. Lending appears as the "Banco de Títulos" balance per asset, with no ISIN; the balance date is in the page's opening sentence.
- **2024-09-02:** the 2024 layout. Lending open balances by market (`Data Ticker ISIN …`), and registered loans whose rows wrap over several lines.
- **2026-11-05:** the 2026 layout. The header reads `Código IF`, no totals or divisor are printed, and lending headers read `Data Código IF Código ISIN …`.
