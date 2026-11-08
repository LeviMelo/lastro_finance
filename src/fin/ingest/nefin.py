"""NEFIN-USP Brazilian risk factors (docs/sources/nefin.md) -> staging `factor`.

Four CSVs (value- and equally-weighted portfolios, daily and monthly) share one shape, so one wide table holds them
all, source-shaped: `weighting`/`frequency` come from the dataset id, `period_start` is the day (daily) or the first
day of the month (monthly). Values are exact decimals of the CSV text (some use exponent notation, `7.18e-05`);
they are **fractions per period** (0.01 = 1%), `risk_free` the daily (or monthly) rate of the same file. The leading
unnamed row counter of the daily files is not kept: it renumbers when rows are inserted (note §4).
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

import polars as pl

from fin.ingest.base import Parsed
from fin.schema import Column, Contract, Rule

FRACTION = pl.Decimal(38, 24)  # up to 20 decimals measured on 2026-11-07
UNIT = "fraction per period (0.01 = 1%)"
DATASETS = {  # dataset id -> (weighting, frequency)
    "nefin_factors": ("value", "D"),
    "nefin_factors_equally_weighted": ("equal", "D"),
    "nefin_factors_monthly": ("value", "M"),
    "nefin_factors_equally_weighted_monthly": ("equal", "M"),
}
_FACTORS = ("Rm_minus_Rf", "SMB", "HML", "WML", "IML", "Risk_Free")


class LayoutError(ValueError):
    pass


FACTOR = Contract(
    table="staging.nefin.factor",
    version=1,
    description="NEFIN risk factors of one period (market excess return, SMB, HML, WML, IML, risk-free).",
    columns=(
        Column(
            "weighting",
            pl.String,
            "value (value-weighted) or equal (equally-weighted) portfolios",
            "ponderação",
            nullable=False,
        ),
        Column("frequency", pl.String, "D daily, M monthly", "periodicidade", nullable=False),
        Column(
            "period_start", pl.Date, "the day (D) or the first day of the month (M)", "início do período", "date", False
        ),
        Column("rm_minus_rf", FRACTION, "Rm_minus_Rf: market excess return", "prêmio de mercado", UNIT),
        Column("smb", FRACTION, "SMB: small minus big", "SMB", UNIT),
        Column("hml", FRACTION, "HML: high minus low (book-to-market)", "HML", UNIT),
        Column("wml", FRACTION, "WML: winners minus losers (momentum)", "WML", UNIT),
        Column("iml", FRACTION, "IML: illiquid minus liquid", "IML", UNIT),
        Column("risk_free", FRACTION, "Risk_Free: risk-free rate of the period", "taxa livre de risco", UNIT),
    ),
    rules=(
        Rule("frequency_known", pl.col("frequency").is_in(["D", "M"])),
        Rule(
            "all_factors_present",
            pl.all_horizontal(
                pl.col(c).is_not_null() for c in ("rm_minus_rf", "smb", "hml", "wml", "iml", "risk_free")
            ),
        ),
    ),
    key=("weighting", "frequency", "period_start", "raw_sha256"),
)
CONTRACTS = {"factor": FACTOR}


def _dec(text: str, where: str) -> Decimal | None:
    if text.strip() == "":
        return None
    try:
        return Decimal(text)
    except InvalidOperation as e:
        raise LayoutError(f"{where}: not a number {text!r}") from e


def parse_factors(blob: bytes, row: dict[str, Any]) -> pl.DataFrame:
    ds = str(row["dataset_id"])
    if ds not in DATASETS:
        raise LayoutError(f"unknown NEFIN dataset {ds!r}")
    weighting, freq = DATASETS[ds]
    reader = csv.reader(io.StringIO(blob.decode("utf-8")))
    header = next(reader)
    want = ["", "Date", *_FACTORS] if freq == "D" else ["year", "month", *_FACTORS]
    if header != want:
        raise LayoutError(f"{ds}: header {header} is not the expected {want}")
    rows: list[dict[str, Any]] = []
    for n, rec in enumerate(reader, start=2):
        if len(rec) != len(want):
            raise LayoutError(f"{ds} line {n}: {len(rec)} fields")
        start = date.fromisoformat(rec[1]) if freq == "D" else date(int(rec[0]), int(rec[1]), 1)
        v = [_dec(x, f"{ds} line {n}") for x in rec[2:]]
        rows.append(
            {
                "weighting": weighting,
                "frequency": freq,
                "period_start": start,
                **dict(zip(("rm_minus_rf", "smb", "hml", "wml", "iml", "risk_free"), v, strict=True)),
                "raw_locator": f"line={n}",
            }
        )
    schema = {c.name: c.dtype for c in FACTOR.columns} | {"raw_locator": pl.String}
    df = pl.DataFrame(rows, schema=schema, orient="row")
    return df.with_columns(
        pl.lit(row["raw_sha256"]).alias("raw_sha256"), pl.lit(row["ingest_run_id"]).alias("ingest_run_id")
    )


def parse_payload(blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
    yield Parsed("factor", str(row["dataset_id"]), parse_factors(blob, row))
