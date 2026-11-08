"""B3 reference rates, `TS<YYMMDD>.ex_` of pesquisapregao (docs/sources/b3_reference_rates.md) -> staging `swap_rate`.

The archived object is a zip holding `TS<YYMMDD>.ex_`, a PKWARE self-extracting EXE that holds a second zip with
`TaxaSwap.txt` (member name casing varies by year: `TAXASWAP.TXT`, `TaxasSwap.txt`). **Nothing is ever executed**:
both layers are read with `zipfile` (the EXE prefix is skipped by the zip reader).

`TaxaSwap.txt` is fixed width, CRLF, ISO-8859-1, no header; one row per curve vertex of a day (all B3 curves, ~31,000
rows in 2026). No official layout was found (note §3, §7): the positions below were inferred from data and
cross-checked against B3's web CSV (DIC curve: 282/282 vertices identical in days, calendar days and rate). Three
widths exist, each a different era (measured over all 6,413 archived days):

    pos (0-based)  field
    0-5            sequence in the file (not kept)
    6-10           constant `00101`
    11-18          date AAAAMMDD
    19-20          constant `T1`
    21-23          curve code (`PRE`, `DIC`, `DOL`, `TR`, `INP`...)
    26-40          curve description (15 chars)
    41-45 / 46-50  calendar days / business days to the vertex
    51             sign
    52-...         value, integer with 7 implied decimals
    width 65 (2000..2002-10-24): value 12 digits, then a space
    width 67 (2002-10-25..2003-05-15): value 14 digits, then a space
    width 72 (2003-05-16..): value 14 digits, vertex type F|M, a 5-digit field

The 5-digit field equals the vertex's nominal calendar days in the samples (1, 7, 2520...), but its meaning is not
documented; it is kept as published (`vertex_nominal`). Curve units differ (PRE/DIC: % a.a.; INP/IPC are index-like
levels): `value` is stored as published and the unit follows the curve code.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Iterable
from datetime import date
from typing import Any

import polars as pl

from fin.ingest.base import NotData, Parsed
from fin.schema import Column, Contract, Rule

VALUE = pl.Decimal(38, 7)


class LayoutError(ValueError):
    pass


SWAP_RATE = Contract(
    table="staging.b3_reference_rates.swap_rate",
    version=1,
    description="One vertex of one B3 reference curve (TaxaSwap.txt) on a day, as published.",
    columns=(
        Column("ref_date", pl.Date, "date inside the record (AAAAMMDD)", "data", "date", nullable=False),
        Column(
            "curve_code", pl.String, "curve code, 3 chars: PRE, DIC, DOL, TR, INP...", "código da curva", nullable=False
        ),
        Column("curve_description", pl.String, "curve description as published (15 chars, trimmed)", "descrição"),
        Column("calendar_days", pl.Int32, "dias corridos to the vertex", "dias corridos", "calendar days", False),
        Column("business_days", pl.Int32, "dias úteis to the vertex", "dias úteis", "business days", False),
        Column(
            "value",
            VALUE,
            "rate or level of the vertex; integer with 7 implied decimals in the file",
            "taxa/valor",
            "% a.a. for rate curves (PRE, DIC...); index-like level for INP/IPC; per curve_code",
            False,
        ),
        Column("vertex_type", pl.String, "F or M (meaning not documented); null before 2003-05-16", "tipo de vértice"),
        Column(
            "vertex_nominal",
            pl.Int32,
            "last 5-digit field (nominal vertex, calendar days in samples); null before 2003-05-16",
            "vértice nominal",
            "as published",
        ),
        Column(
            "file_date",
            pl.Date,
            "the date of the file requested (manifest); differs from ref_date if B3 served another day's rows",
            "data do arquivo",
            "date",
        ),
    ),
    rules=(
        Rule("days_non_negative", (pl.col("calendar_days") >= 0) & (pl.col("business_days") >= 0)),
        Rule("vertex_type_known", pl.col("vertex_type").is_null() | pl.col("vertex_type").is_in(["F", "M"])),
    ),
    key=("ref_date", "curve_code", "calendar_days", "business_days", "raw_sha256"),
)
CONTRACTS = {"swap_rate": SWAP_RATE}

# width -> (value digits, has vertex type and nominal vertex)
WIDTHS = {65: (12, False), 67: (14, False), 72: (14, True)}


def taxa_swap_text(blob: bytes) -> bytes:
    """`TaxaSwap.txt` bytes from the archived pesquisapregao object (zip -> PKSFX exe -> zip). Never executed."""
    try:
        outer = zipfile.ZipFile(io.BytesIO(blob))
        names = outer.namelist()
        if len(names) != 1:
            raise LayoutError(f"B3 TS: expected one member in the download, got {names}")
        inner = zipfile.ZipFile(io.BytesIO(outer.read(names[0])))
        members = inner.namelist()
        if len(members) != 1:
            raise LayoutError(f"B3 TS: expected one file in the self-extractor, got {members}")
        return inner.read(members[0])
    except zipfile.BadZipFile as e:
        raise NotData(f"B3 TS: not a zip ({e})") from e


def parse_taxa_swap(text: bytes, row: dict[str, Any]) -> pl.DataFrame:
    """Vectorised fixed-width parse of `TaxaSwap.txt`; a layout that differs from the three known ones raises."""
    lines = [ln for ln in text.decode("latin-1").split("\r\n") if ln]
    if not lines:
        raise NotData("B3 TS: empty TaxaSwap.txt")
    df = pl.DataFrame({"line": lines}).with_row_index("n", offset=1)
    widths = df["line"].str.len_chars().unique().to_list()
    if len(widths) != 1 or widths[0] not in WIDTHS:
        raise LayoutError(f"B3 TS: line widths {sorted(widths)} are not one of {sorted(WIDTHS)}")
    vdigits, extended = WIDTHS[widths[0]]
    s = pl.col("line").str.slice
    bad = df.filter((s(6, 5) != "00101") | (s(19, 2) != "T1") | ~s(51, 1).is_in(["+", "-"])).height
    if bad:
        raise LayoutError(f"B3 TS: {bad} lines do not match the fixed layout (constants/sign)")
    digits = s(52, vdigits)
    int_part, dec_part = digits.str.slice(0, vdigits - 7), digits.str.slice(vdigits - 7, 7)
    value = (pl.when(s(51, 1) == "-").then(pl.lit("-")).otherwise(pl.lit("")) + int_part + "." + dec_part).cast(VALUE)
    file_date = row.get("source_reference_date")
    out = df.select(
        s(11, 8).str.to_date("%Y%m%d").alias("ref_date"),
        s(21, 3).str.strip_chars().alias("curve_code"),
        s(26, 15).str.strip_chars().alias("curve_description"),
        s(41, 5).cast(pl.Int32).alias("calendar_days"),
        s(46, 5).cast(pl.Int32).alias("business_days"),
        value.alias("value"),
        (s(52 + vdigits, 1) if extended else pl.lit(None, dtype=pl.String)).alias("vertex_type"),
        (s(53 + vdigits, 5).cast(pl.Int32) if extended else pl.lit(None, dtype=pl.Int32)).alias("vertex_nominal"),
        pl.lit(file_date if isinstance(file_date, date) else None, dtype=pl.Date).alias("file_date"),
        pl.format("line={}", pl.col("n")).alias("raw_locator"),
        pl.lit(row["raw_sha256"]).alias("raw_sha256"),
        pl.lit(row["ingest_run_id"]).alias("ingest_run_id"),
    )
    return out


def parse_payload(blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
    if str(row["dataset_id"]) != "TS":  # the PR (BVBG.086) zips of the same connector are not parsed here
        return
    df = parse_taxa_swap(taxa_swap_text(blob), row)
    dates = df["ref_date"].unique().to_list()
    yield Parsed("swap_rate", f"ref_date={dates[0]}" if len(dates) == 1 else "mixed", df)
