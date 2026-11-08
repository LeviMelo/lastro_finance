"""CVM FRE (Formulário de Referência) yearly zip -> staging `document` and `capital_social` (docs/sources/cvm_fre.md).

Only two members are parsed:
- the index `fre_cia_aberta_<Y>.csv`: every delivered version, with its delivery date (the knowledge date);
- `capital_social`: capital and share counts (whole shares) of the latest version of each company's FRE.

The other members are not parsed. Some hold personal data of administrators and of shareholders.
cp1252, `;`, header checked.
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

INDEX = {
    "CNPJ_CIA": "cnpj",
    "DT_REFER": "reference_date",
    "VERSAO": "version",
    "DENOM_CIA": "company_name",
    "CD_CVM": "cd_cvm",
    "CATEG_DOC": "category",
    "ID_DOC": "doc_id",
    "DT_RECEB": "received_on",
    "LINK_DOC": "link",
}
CAPITAL = {
    "CNPJ_Companhia": "cnpj",
    "Data_Referencia": "reference_date",
    "Versao": "version",
    "ID_Documento": "doc_id",
    "Nome_Companhia": "company_name",
    "ID_Capital_Social": "capital_id",
    "Tipo_Capital": "capital_type",
    "Data_Autorizacao_Aprovacao": "approved_on",
    "Valor_Capital": "capital_brl",
    "Prazo_Integralizacao": "payment_term",
    "Quantidade_Acoes_Ordinarias": "common",
    "Quantidade_Acoes_Preferenciais": "preferred",
    "Quantidade_Total_Acoes": "total",
}
DATES = {"reference_date", "received_on", "approved_on"}
INTS = {"version": pl.Int16, "common": pl.Int64, "preferred": pl.Int64, "total": pl.Int64}
KEYS = {"cnpj", "reference_date", "version", "doc_id"}


class LayoutError(ValueError):
    pass


def _dtype(v: str) -> Any:
    if v in DATES:
        return pl.Date
    if v == "capital_brl":
        return pl.Decimal(20, 2)
    return INTS.get(v, pl.String)


def _contract(table: str, desc: str, cols: dict[str, str]) -> Contract:
    return Contract(
        table=f"staging.cvm_fre.{table}",
        version=1,
        description=desc,
        columns=tuple(
            Column(
                v,
                _dtype(v),
                f"{k} as written" + ("; whole shares" if v in ("common", "preferred", "total") else ""),
                k.lower(),
                "date" if v in DATES else ("BRL" if v == "capital_brl" else ("shares" if v in INTS else "")),
                nullable=v not in KEYS,
            )
            for k, v in cols.items()
        ),
    )


DOCUMENT = _contract("document", "An FRE version as CVM's yearly index lists it.", INDEX)
CAPITAL_SOCIAL = _contract(
    "capital_social", "A capital row (issued, subscribed, paid in) of the latest FRE version.", CAPITAL
)
CONTRACTS = {"document": DOCUMENT, "capital_social": CAPITAL_SOCIAL}


def _cast(k: str, v: str) -> pl.Expr:
    c = pl.col(k).str.strip_chars()
    if v in DATES:
        return c.str.strptime(pl.Date, "%Y-%m-%d", strict=False).alias(v)
    if v == "capital_brl":
        return c.cast(pl.Decimal(20, 2), strict=False).alias(v)
    if v in INTS:
        return c.cast(INTS[v], strict=False).alias(v)
    return pl.col(k).alias(v)


def parse_member(data: bytes, name: str, cols: dict[str, str], row: dict[str, Any]) -> pl.DataFrame:
    text = data.decode("cp1252")
    head = text.split("\n", 1)[0].rstrip("\r").split(";")
    if head != list(cols):
        raise LayoutError(f"FRE {name}: header changed: {head}")
    df = pl.read_csv(io.StringIO(text), separator=";", infer_schema=False, quote_char=None)
    return df.with_row_index("i", offset=2).select(
        *[_cast(k, v) for k, v in cols.items()],
        pl.lit(row["raw_sha256"]).alias("raw_sha256"),
        (pl.lit(f"member={name};line=") + pl.col("i").cast(pl.String)).alias("raw_locator"),
        pl.lit(row["ingest_run_id"]).alias("ingest_run_id"),
    )


def parse_payload(blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
    notes = row.get("notes") or ""
    if "|" in notes:  # an unpacked member (ADR-0014)
        members = [(notes.split("|", 1)[1], blob)]
    elif blob[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            members = [(n, z.read(n)) for n in z.namelist()]
    else:
        return  # the JSON record of an unpacked zip
    for name, data in members:
        m = re.fullmatch(r"fre_cia_aberta_(?:(capital_social)_)?(\d{4})\.csv", name)
        if not m:
            continue  # members not parsed (see the module docstring)
        if m.group(1):
            yield Parsed("capital_social", f"year={m.group(2)}", parse_member(data, name, CAPITAL, row))
        else:
            yield Parsed("document", f"year={m.group(2)}", parse_member(data, name, INDEX, row))
