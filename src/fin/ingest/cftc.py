"""CFTC Commitments of Traders, futures only -> staging `position` (docs/sources/context_global.md, cftc_cot).

Three yearly zips: legacy (`deacot<YYYY>`), disaggregated (`fut_disagg_txt_<YYYY>`) and traders in financial futures
(`fut_fin_txt_<YYYY>`). Each row of a file is one market on one Tuesday. Staged long and declared: one row per
(report, market, date, trader group, side) for the "All" position columns and open interest. Week-on-week changes,
percentages of open interest and trader counts are derivable or secondary and stay in raw.

Headers measured on all 51 files (2010-2026): one per report, except that the disaggregated and financial reports
name their date column `Report_Date_as_MM_DD_YYYY` in 2010-2012 (holding ISO dates despite the name) and
`Report_Date_as_YYYY-MM-DD` later.
"""

from __future__ import annotations

import csv
import io
import zipfile
from collections.abc import Iterable
from typing import Any

import polars as pl

from fin.ingest.base import Parsed
from fin.schema import Column, Contract, Rule

# report -> {header: (trader group, side)}; "open_interest" has group "all", side "total"
LEGACY = {
    "Open Interest (All)": ("all", "open_interest"),
    "Noncommercial Positions-Long (All)": ("noncommercial", "long"),
    "Noncommercial Positions-Short (All)": ("noncommercial", "short"),
    "Noncommercial Positions-Spreading (All)": ("noncommercial", "spread"),
    "Commercial Positions-Long (All)": ("commercial", "long"),
    "Commercial Positions-Short (All)": ("commercial", "short"),
    " Total Reportable Positions-Long (All)": ("reportable", "long"),
    "Total Reportable Positions-Short (All)": ("reportable", "short"),
    "Nonreportable Positions-Long (All)": ("nonreportable", "long"),
    "Nonreportable Positions-Short (All)": ("nonreportable", "short"),
}
DISAGG = {
    "Open_Interest_All": ("all", "open_interest"),
    "Prod_Merc_Positions_Long_All": ("producer_merchant", "long"),
    "Prod_Merc_Positions_Short_All": ("producer_merchant", "short"),
    "Swap_Positions_Long_All": ("swap_dealer", "long"),
    "Swap__Positions_Short_All": ("swap_dealer", "short"),
    "Swap__Positions_Spread_All": ("swap_dealer", "spread"),
    "M_Money_Positions_Long_All": ("managed_money", "long"),
    "M_Money_Positions_Short_All": ("managed_money", "short"),
    "M_Money_Positions_Spread_All": ("managed_money", "spread"),
    "Other_Rept_Positions_Long_All": ("other_reportable", "long"),
    "Other_Rept_Positions_Short_All": ("other_reportable", "short"),
    "Other_Rept_Positions_Spread_All": ("other_reportable", "spread"),
    "NonRept_Positions_Long_All": ("nonreportable", "long"),
    "NonRept_Positions_Short_All": ("nonreportable", "short"),
}
FIN = {
    "Open_Interest_All": ("all", "open_interest"),
    "Dealer_Positions_Long_All": ("dealer", "long"),
    "Dealer_Positions_Short_All": ("dealer", "short"),
    "Dealer_Positions_Spread_All": ("dealer", "spread"),
    "Asset_Mgr_Positions_Long_All": ("asset_manager", "long"),
    "Asset_Mgr_Positions_Short_All": ("asset_manager", "short"),
    "Asset_Mgr_Positions_Spread_All": ("asset_manager", "spread"),
    "Lev_Money_Positions_Long_All": ("leveraged_funds", "long"),
    "Lev_Money_Positions_Short_All": ("leveraged_funds", "short"),
    "Lev_Money_Positions_Spread_All": ("leveraged_funds", "spread"),
    "Other_Rept_Positions_Long_All": ("other_reportable", "long"),
    "Other_Rept_Positions_Short_All": ("other_reportable", "short"),
    "Other_Rept_Positions_Spread_All": ("other_reportable", "spread"),
    "NonRept_Positions_Long_All": ("nonreportable", "long"),
    "NonRept_Positions_Short_All": ("nonreportable", "short"),
}
REPORTS = {  # dataset id -> (report, name column, contract code column, date columns (format), fields)
    "deacot": ("legacy", "Market and Exchange Names", "CFTC Contract Market Code",
               {"As of Date in Form YYYY-MM-DD": "%Y-%m-%d"}, LEGACY),
    "fut_disagg_txt": ("disaggregated", "Market_and_Exchange_Names", "CFTC_Contract_Market_Code",
                       {"Report_Date_as_YYYY-MM-DD": "%Y-%m-%d", "Report_Date_as_MM_DD_YYYY": "%Y-%m-%d"}, DISAGG),
    "fut_fin_txt": ("financial", "Market_and_Exchange_Names", "CFTC_Contract_Market_Code",
                    {"Report_Date_as_YYYY-MM-DD": "%Y-%m-%d", "Report_Date_as_MM_DD_YYYY": "%Y-%m-%d"}, FIN),
}  # fmt: skip


class LayoutError(ValueError):
    pass


POSITION = Contract(
    table="staging.cftc_cot.position",
    version=1,
    description="Futures positions of one trader group on one side, in one market, on one report date.",
    columns=(
        Column("report", pl.String, "legacy, disaggregated or financial", "relatório", nullable=False),
        Column("market_code", pl.String, "CFTC contract market code", "código do mercado", nullable=False),
        Column("market_name", pl.String, "market and exchange names as written", "mercado", nullable=False),
        Column("report_date", pl.Date, "the Tuesday the positions are as of", "data", "date", nullable=False),
        Column(
            "trader_group",
            pl.String,
            "commercial, managed_money, dealer… ('all' for open interest)",
            "grupo",
            nullable=False,
        ),
        Column("side", pl.String, "long, short, spread or open_interest", "lado", nullable=False),
        Column("contracts", pl.Int64, "number of futures contracts", "contratos", "contracts", nullable=False),
    ),
    rules=(Rule("non_negative", pl.col("contracts") >= 0),),
)
CONTRACTS = {"position": POSITION}


def parse_report(blob: bytes, row: dict[str, Any]) -> pl.DataFrame:
    ds = str(row["dataset_id"])
    if ds not in REPORTS:
        raise LayoutError(f"CFTC: unknown dataset {ds}")
    report, name_col, code_col, date_cols, fields = REPORTS[ds]
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        names = z.namelist()
        if len(names) != 1:
            raise LayoutError(f"CFTC {ds}: members {names}")
        # some older files put a space after a closing quote (`"CANADIAN DOLLAR - …" ,`): Python's csv reads it
        reader = csv.reader(io.StringIO(z.read(names[0]).decode("latin-1")))
        header = next(reader)
        body = [r for r in reader if r]
        df = pl.DataFrame({h.strip('"'): [r[j].strip() if j < len(r) else None for r in body]
                           for j, h in enumerate(header) if h.strip('"')})  # fmt: skip
        df = df.rename(
            {c: c.strip() if c.strip() in fields or c.strip() in (name_col, code_col) else c for c in df.columns}
        )
    date_col = next((c for c in date_cols if c in df.columns), None)
    missing = [c for c in [name_col, code_col, *fields] if c not in df.columns]
    if date_col is None or missing:
        raise LayoutError(f"CFTC {ds}: missing columns {missing or list(date_cols)}")
    base = df.with_row_index("i", offset=2).select(
        pl.lit(report).alias("report"),
        pl.col(code_col).str.strip_chars().alias("market_code"),
        pl.col(name_col).str.strip_chars().alias("market_name"),
        pl.col(date_col).str.strip_chars().str.strptime(pl.Date, date_cols[date_col]).alias("report_date"),
        "i",
        *[pl.col(c).str.strip_chars().alias(c) for c in fields],
    )
    long = base.unpivot(index=["report", "market_code", "market_name", "report_date", "i"], on=list(fields),
                        variable_name="field", value_name="text")  # fmt: skip
    groups = {k: v[0] for k, v in fields.items()}
    sides = {k: v[1] for k, v in fields.items()}
    return long.select(
        "report",
        "market_code",
        "market_name",
        "report_date",
        pl.col("field").replace_strict(groups).alias("trader_group"),
        pl.col("field").replace_strict(sides).alias("side"),
        pl.col("text").cast(pl.Int64).alias("contracts"),
        pl.lit(row["raw_sha256"]).alias("raw_sha256"),
        (pl.lit(f"member={names[0]};line=") + pl.col("i").cast(pl.String) + ";column=" + pl.col("field")).alias(
            "raw_locator"
        ),
        pl.lit(row["ingest_run_id"]).alias("ingest_run_id"),
    )


def parse_payload(blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
    df = parse_report(blob, row)
    year = df["report_date"].dt.year().max() if df.height else 0
    yield Parsed("position", f"report={row['dataset_id']}/year={year}", df)
