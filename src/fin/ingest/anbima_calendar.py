"""ANBIMA national holidays file -> staging `holiday` -> core `calendar_day` (docs/sources/anbima_calendar.md).

The file is one BIFF8 sheet `Feriados`: a header row, then rows of (Excel date serial, weekday name, holiday name),
then a footer (`Fonte: ANBIMA` and notes). Parsing stops at the first row whose first cell is not a date; every
footer row must be text, otherwise the layout has changed and the parse fails loudly.

The core calendar is built from the most recently fetched version of the file. Earlier versions stay in staging,
keyed by their SHA-256, so a calendar "as known at K" can be rebuilt.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Any, ClassVar

import polars as pl
import xlrd

from fin.config import Zones
from fin.ingest.base import Connector, Mode, Parsed
from fin.ingest.fetch import FetchSpec
from fin.reference.calendar import build_calendar_days, extend_back
from fin.schema import Column, Contract, Rule
from fin.store.manifest import Manifest
from fin.store.runs import IngestRun
from fin.store.tables import read_parquet_dir, write_parquet

URL = "https://www.anbima.com.br/feriados/arqs/feriados_nacionais.xls"
SHEET = "Feriados"
HEADER = ["Data", "Dia da Semana", "Feriado"]

HOLIDAY = Contract(
    table="staging.anbima_calendar.holiday",
    version=1,
    description="One row per holiday as listed in ANBIMA's feriados_nacionais.xls.",
    columns=(
        Column("date", pl.Date, "holiday date", "data do feriado", "date", nullable=False),
        Column("weekday_pt", pl.String, "weekday as written by ANBIMA", "dia da semana", nullable=False),
        Column("name", pl.String, "holiday name, whitespace-stripped", "nome do feriado", nullable=False),
    ),
    rules=(
        Rule(
            "weekday_matches_date",
            pl.col("weekday_pt")
            .str.to_lowercase()
            .str.contains(
                pl.col("date")
                .dt.weekday()
                .replace_strict(
                    {1: "segunda", 2: "terça", 3: "quarta", 4: "quinta", 5: "sexta", 6: "sábado", 7: "domingo"},
                    return_dtype=pl.String,
                )
            ),
        ),
    ),
    key=("date",),
)


class LayoutError(ValueError):
    pass


def parse_holidays(blob: bytes) -> pl.DataFrame:
    book = xlrd.open_workbook(file_contents=blob)
    sheet = book.sheet_by_name(SHEET)
    header = [str(sheet.cell_value(0, c)).strip() for c in range(3)]
    if header != HEADER:
        raise LayoutError(f"unexpected header {header}")
    dates: list[date] = []
    weekdays: list[str] = []
    names: list[str] = []
    locators: list[str] = []
    r = 1
    while r < sheet.nrows and sheet.cell_type(r, 0) == xlrd.XL_CELL_DATE:
        dates.append(xlrd.xldate_as_datetime(float(sheet.cell_value(r, 0)), book.datemode).date())
        weekdays.append(str(sheet.cell_value(r, 1)).strip())
        names.append(str(sheet.cell_value(r, 2)).strip())
        locators.append(f"sheet={SHEET};row={r + 1}")
        r += 1
    for rr in range(r, sheet.nrows):
        if sheet.cell_type(rr, 0) not in (xlrd.XL_CELL_TEXT, xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
            raise LayoutError(f"non-text footer cell at row {rr + 1}: the layout has changed")
    if not dates:
        raise LayoutError("no holiday rows")
    return pl.DataFrame(
        {"date": dates, "weekday_pt": weekdays, "name": names, "raw_locator": locators},
        schema={"date": pl.Date, "weekday_pt": pl.String, "name": pl.String, "raw_locator": pl.String},
    )


class AnbimaCalendar(Connector):
    source_id: ClassVar[str] = "anbima_calendar"
    version: ClassVar[str] = "1"
    contracts: ClassVar[dict[str, Contract]] = {"holiday": HOLIDAY}

    def discover(self, mode: Mode, zones: Zones, **options: Any) -> Iterable[FetchSpec]:
        yield FetchSpec(self.source_id, "feriados_nacionais", URL, "xls")

    def parse(self, blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
        df = parse_holidays(blob).with_columns(
            pl.lit(row["raw_sha256"]).alias("raw_sha256"), pl.lit(row["ingest_run_id"]).alias("ingest_run_id")
        )
        yield Parsed("holiday", "all", df)

    def derive(self, zones: Zones, run: IngestRun) -> None:
        manifest = (
            Manifest(zones.manifest)
            .read()
            .filter((pl.col("source_id") == self.source_id) & pl.col("http_status").is_in([200, 304]))
        )
        if manifest.is_empty():
            return
        latest = manifest.sort("fetched_at")["raw_sha256"][-1]
        staged = read_parquet_dir(zones.staging / self.source_id / "holiday")
        if staged is None:
            raise RuntimeError("anbima_calendar: no staged holidays to build the calendar from")
        holidays = staged.filter(pl.col("raw_sha256") == latest).select("date", "name")
        build_calendar(zones, run, build_calendar_days(holidays, latest))


def build_calendar(zones: Zones, run: IngestRun | None, days: pl.DataFrame | None = None) -> None:
    """Write core `calendar_day`: ANBIMA's days, extended back with SGS 12 publication days (OQ-22). Called by the
    ANBIMA calendar and by BCB SGS (whichever loads last completes it)."""
    path = zones.core / "reference" / "calendar_day" / "calendar_day.parquet"
    if days is None:
        if not path.exists():
            return
        days = pl.read_parquet(path).filter(pl.col("basis") == "anbima") if "basis" in pl.read_parquet_schema(
            path) else pl.read_parquet(path).with_columns(pl.lit("anbima").alias("basis"))  # fmt: skip
    obs = zones.core / "series_observation" / "source=bcb_sgs.parquet"
    pub: list[date] = []
    if obs.exists():
        pub = (
            pl.scan_parquet(obs)
            .filter(pl.col("series_id") == "bcb_sgs:12")
            .select(pl.col("vt_reference").str.to_date(strict=False).alias("d"))
            .drop_nulls()
            .unique()
            .collect()["d"]
            .to_list()
        )
    full = extend_back(days, pub)
    write_parquet(full, path)
    if run is not None:
        run.count("calendar_day", in_=days.height, out=full.height)


def load_calendar(zones: Zones) -> pl.DataFrame:
    path = zones.core / "reference" / "calendar_day" / "calendar_day.parquet"
    if not path.exists():
        raise FileNotFoundError("no calendar: run `fin ingest anbima_calendar` first")
    return pl.read_parquet(path)
