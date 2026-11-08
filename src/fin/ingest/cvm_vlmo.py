"""CVM VLMO: securities traded and held by a company's insiders, by role (docs/sources/cvm_vlmo.md).

`vlmo_cia_aberta_YYYY.zip` (2018-) holds two cp1252 CSVs: the index of filings (`document`: one row per company,
month and version, with the delivery date = knowledge time) and the consolidated positions and movements
(`movement`: one row per company, month, version, role group, asset and movement). Measured on 2018 and 2025
(2026-11-08): every version is kept in both members (382 of 5,397 company-months of 2025 have more than one);
quantities are signed integers up to 12 digits; prices and volumes have 10 decimals.

Holdings are reported by role group (controller, board, officers, fiscal council, other bodies), never by person.
Two free-text fields are not parsed because they can name people: `Descricao_Movimentacao` and
`Motivo_Reapresentacao` (one 2025 re-filing names the staff who helped).
"""

from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Iterable
from typing import Any

import polars as pl

from fin.ingest.base import Parsed
from fin.schema import Column, Contract, Rule

PRICE = pl.Decimal(38, 10)


class LayoutError(ValueError):
    pass


# header -> (column, dtype, en, pt, unit); None: not parsed
INDEX: dict[str, tuple[str, Any, str, str, str] | None] = {
    "CNPJ_Companhia": ("company_cnpj", pl.String, "company CNPJ, 14 digits", "CNPJ da companhia", ""),
    "Nome_Companhia": ("company_name", pl.String, "company name as written", "nome da companhia", ""),
    "Data_Referencia": ("reference_month", pl.Date, "first day of the month reported", "mês de referência", "date"),
    "Versao": ("version", pl.Int32, "filing version", "versão", ""),
    "Codigo_CVM": ("cd_cvm", pl.String, "CVM company code", "código CVM", ""),
    "Categoria": ("category", pl.String, "Categoria as written", "categoria", ""),
    "Tipo": ("kind", pl.String, "Tipo as written", "tipo", ""),
    "Data_Entrega": ("delivered_on", pl.Date, "delivery date (knowledge date)", "data de entrega", "date"),
    "Tipo_Apresentacao": ("presentation", pl.String, "AP (first) or RE (re-filing) as written", "apresentação", ""),
    "Motivo_Reapresentacao": None,  # free text that can name people
    "Protocolo_Entrega": ("protocol", pl.String, "delivery protocol", "protocolo de entrega", ""),
    "Link_Download": ("download_url", pl.String, "RAD download link", "link de download", ""),
}
MOVEMENT_COLS: dict[str, tuple[str, Any, str, str, str] | None] = {
    "CNPJ_Companhia": INDEX["CNPJ_Companhia"],
    "Nome_Companhia": INDEX["Nome_Companhia"],
    "Data_Referencia": INDEX["Data_Referencia"],
    "Versao": INDEX["Versao"],
    "Tipo_Empresa": ("entity_kind", pl.String, "Companhia, Controladora or Controlada", "tipo de empresa", ""),
    "Empresa": ("entity_name", pl.String, "the company whose securities they are", "empresa", ""),
    "Tipo_Cargo": ("role_group", pl.String, "role group of the holders (or empty)", "tipo de cargo", ""),
    "Tipo_Movimentacao": ("movement", pl.String, "Tipo_Movimentacao as written", "tipo de movimentação", ""),
    "Descricao_Movimentacao": None,  # free text that can name people
    "Tipo_Operacao": ("direction", pl.String, "Crédito or Débito", "tipo de operação", ""),
    "Tipo_Ativo": ("asset_kind", pl.String, "Tipo_Ativo as written (Ações, Units, Debêntures…)", "tipo de ativo", ""),
    "Caracteristica_Valor_Mobiliario": (
        "security_class",
        pl.String,
        "class as written (ON, PN, a ticker or free text)",
        "característica",
        "",
    ),
    "Intermediario": ("intermediary", pl.String, "broker as written", "intermediário", ""),
    "Data_Movimentacao": ("movement_date", pl.Date, "date of the movement", "data da movimentação", "date"),
    "Quantidade": ("quantity", pl.Int64, "quantity, signed as written", "quantidade", "count"),
    "Preco_Unitario": ("unit_price_brl", PRICE, "unit price", "preço unitário", "BRL per unit"),
    "Volume": ("volume_brl", PRICE, "volume", "volume", "BRL"),
}
KEYS = {"company_cnpj", "reference_month", "version"}


def _contract(table: str, desc: str, cols: dict[str, tuple[str, Any, str, str, str] | None]) -> Contract:
    return Contract(
        table=f"staging.cvm_vlmo.{table}",
        version=1,
        description=desc,
        columns=tuple(
            Column(c[0], c[1], c[2], c[3], c[4], nullable=c[0] not in KEYS) for c in cols.values() if c is not None
        ),
        rules=(Rule("cnpj_14_digits", pl.col("company_cnpj").str.contains(r"^\d{14}$")),),
    )


DOCUMENT = _contract("document", "A VLMO filing (company, month, version) with its delivery date.", INDEX)
MOVEMENT = _contract(
    "movement", "Insider positions and movements of a VLMO filing, by role group, asset and movement.", MOVEMENT_COLS
)
CONTRACTS = {"document": DOCUMENT, "movement": MOVEMENT}


def _cast(head: str, spec: tuple[str, Any, str, str, str]) -> pl.Expr:
    name, dtype = spec[0], spec[1]
    c = pl.col(head).str.strip_chars()
    if name == "company_cnpj":
        return c.str.replace_all(r"\D", "").alias(name)
    if dtype == pl.Date:
        return c.str.strptime(pl.Date, "%Y-%m-%d", strict=False).alias(name)
    if dtype == pl.String:
        return pl.when(c.str.len_chars() > 0).then(c).alias(name)
    return c.cast(dtype, strict=False).alias(name)


def parse_member(data: bytes, name: str, cols: dict[str, Any], row: dict[str, Any]) -> pl.DataFrame:
    text = data.decode("cp1252")
    head = text.split("\n", 1)[0].rstrip("\r").split(";")
    if head != list(cols):
        raise LayoutError(f"VLMO {name}: header changed: {head}")
    df = pl.read_csv(io.StringIO(text), separator=";", infer_schema=False, quote_char=None)
    kept = {k: v for k, v in cols.items() if v is not None}
    out = df.with_row_index("i", offset=2).select(
        *[_cast(k, v) for k, v in kept.items()],
        pl.lit(row["raw_sha256"]).alias("raw_sha256"),
        (pl.lit(f"member={name};line=") + pl.col("i").cast(pl.String)).alias("raw_locator"),
        pl.lit(row["ingest_run_id"]).alias("ingest_run_id"),
    )
    for k, v in kept.items():  # a value that does not cast is a layout change, never a silent null
        if v[1] != pl.String:
            lost = int((df[k].str.strip_chars().str.len_chars() > 0).sum() - out[v[0]].drop_nulls().len())
            if lost:
                raise LayoutError(f"VLMO {name}: {lost} values of {k} do not cast to {v[1]}")
    for k, v in kept.items():
        if v[1] == PRICE and (df[k].str.extract(r"\.(\d+)$").str.len_chars() > 10).any():
            raise LayoutError(f"VLMO {name}: {k} has more than 10 decimals")
    return out


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
        m = re.fullmatch(r"vlmo_cia_aberta_(con_)?(\d{4})\.csv", name)
        if not m:
            raise LayoutError(f"VLMO: unknown member {name}")
        part = f"year={m.group(2)}"
        if m.group(1):
            yield Parsed("movement", part, parse_member(data, name, MOVEMENT_COLS, row))
        else:
            yield Parsed("document", part, parse_member(data, name, INDEX, row))
