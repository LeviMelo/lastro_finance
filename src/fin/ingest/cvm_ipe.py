"""CVM IPE (documentos eventuais) yearly index -> staging `document` (docs/sources/cvm_ipe.md).

One row per delivered document version: company, category (Fato Relevante, Aviso aos Acionistas, Assembleia…),
type, species, subject, reference and delivery dates (date only: the knowledge date), protocol and the download link.
Columns identical 2003-2026 (measured); cp1252; `;`.
"""

from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Iterable
from typing import Any

import polars as pl

from fin.ingest.base import Parsed
from fin.schema import Column, Contract

COLUMNS = {
    "CNPJ_Companhia": "cnpj",
    "Nome_Companhia": "company_name",
    "Codigo_CVM": "cd_cvm",
    "Data_Referencia": "reference_date",
    "Categoria": "category",
    "Tipo": "doc_type",
    "Especie": "species",
    "Assunto": "subject",
    "Data_Entrega": "delivered_on",
    "Tipo_Apresentacao": "presentation",
    "Protocolo_Entrega": "protocol",
    "Versao": "version",
    "Link_Download": "link",
}
DATES = ("reference_date", "delivered_on")


class LayoutError(ValueError):
    pass


DOCUMENT = Contract(
    table="staging.cvm_ipe.document",
    version=1,
    description="An IPE document version as CVM's yearly index lists it.",
    columns=tuple(
        Column(
            v,
            pl.Date if v in DATES else (pl.Int16 if v == "version" else pl.String),
            f"{k} as written",
            k.lower(),
            "date" if v in DATES else "",
            nullable=v not in ("cnpj", "delivered_on"),  # protocol: empty in the older years (2003-)
        )
        for k, v in COLUMNS.items()
    ),
)
CONTRACTS = {"document": DOCUMENT}


def parse_index(data: bytes, name: str, row: dict[str, Any]) -> pl.DataFrame:
    text = data.decode("cp1252")
    head = text.split("\n", 1)[0].rstrip("\r").split(";")
    if head != list(COLUMNS):
        raise LayoutError(f"IPE {name}: header changed: {head}")
    df = pl.read_csv(io.StringIO(text), separator=";", infer_schema=False, quote_char=None)
    return df.with_row_index("i", offset=2).select(
        *[
            (
                pl.col(k).str.strptime(pl.Date, "%Y-%m-%d", strict=False)
                if v in DATES
                else (pl.col(k).cast(pl.Int16, strict=False) if v == "version" else pl.col(k))
            ).alias(v)
            for k, v in COLUMNS.items()
        ],
        pl.lit(row["raw_sha256"]).alias("raw_sha256"),
        (pl.lit(f"member={name};line=") + pl.col("i").cast(pl.String)).alias("raw_locator"),
        pl.lit(row["ingest_run_id"]).alias("ingest_run_id"),
    )


def parse_payload(blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
    notes = row.get("notes") or ""
    if "|" in notes:  # an unpacked member (ADR-0014)
        name = notes.split("|", 1)[1]
        members = [(name, blob)]
    elif blob[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            members = [(n, z.read(n)) for n in z.namelist()]
    else:
        return  # the JSON record of an unpacked zip
    for name, data in members:
        m = re.search(r"_(\d{4})\.csv$", name)
        if not m:
            raise LayoutError(f"IPE: unexpected member {name}")
        yield Parsed("document", f"year={m.group(1)}", parse_index(data, name, row))
