# cftc_cot fixtures (byte-exact lines of archived files, fetched 2026-11-07)
Each file = the header line + the first 3 lines containing the market name, from the member of:
- `fin_2026_brl.txt` — https://www.cftc.gov/files/dea/history/fut_fin_txt_2026.zip (`FinFutYY.txt`), BRAZILIAN REAL
- `disagg_2010_corn.txt` — https://www.cftc.gov/files/dea/history/fut_disagg_txt_2010.zip (`f_year.txt`), CORN
  (date column named `Report_Date_as_MM_DD_YYYY`, ISO values)
- `legacy_2026_cad.txt` — https://www.cftc.gov/files/dea/history/deacot2026.zip (`annual.txt`), CANADIAN DOLLAR
Tests zip each file the way CFTC ships it (one member).
