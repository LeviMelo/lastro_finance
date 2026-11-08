"""CVM FCA (Formulário Cadastral) yearly zip -> staging `document`, `company` and `security` (docs/sources/cvm_fca.md).

Three members are parsed (cp1252, `;`, header checked, `LayoutError` on any change):
- the index `fca_cia_aberta_<Y>.csv`: every delivered version with its delivery date (the knowledge time);
- `geral`: company identity (names, CVM code, registration category and status, sector, controller type, fiscal-year
  end) of the latest version of each filing;
- `valor_mobiliario`: the securities the company has listed (class, trading code, market, segment, listing and
  trading dates): the time-ranged CNPJ -> ticker evidence of PLAN §4.4.

Not parsed, on purpose: `endereco`, `departamento_acionistas`, `dri`, `escriturador` and `auditor` (addresses, phones,
e-mails, named individuals and their CPF), `canal_divulgacao` and `pais_estrangeiro_negociacao`. In `geral` the web
address is not kept either. A value that does not cast to its type raises: nothing is nulled silently.
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

INDEX: dict[str, str | None] = {
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
_KEY: dict[str, str | None] = {
    "CNPJ_Companhia": "cnpj",
    "Data_Referencia": "reference_date",
    "Versao": "version",
    "ID_Documento": "doc_id",
    "Nome_Empresarial": "company_name",
}
GERAL: dict[str, str | None] = {  # the whole header, in file order; None drops the column (contact data)
    **_KEY,
    "Data_Nome_Empresarial": "name_since",
    "Nome_Empresarial_Anterior": "previous_name",
    "Data_Constituicao": "incorporated_on",
    "Codigo_CVM": "cvm_code",
    "Data_Registro_CVM": "registered_on",
    "Categoria_Registro_CVM": "registration_category",
    "Data_Categoria_Registro_CVM": "registration_category_since",
    "Situacao_Registro_CVM": "registration_status",
    "Data_Situacao_Registro_CVM": "registration_status_since",
    "Pais_Origem": "country_of_origin",
    "Pais_Custodia_Valores_Mobiliarios": "securities_custody_country",
    "Setor_Atividade": "sector",
    "Descricao_Atividade": "activity_description",
    "Situacao_Emissor": "issuer_phase",
    "Data_Situacao_Emissor": "issuer_phase_since",
    "Especie_Controle_Acionario": "control_type",
    "Data_Especie_Controle_Acionario": "control_type_since",
    "Dia_Encerramento_Exercicio_Social": "fiscal_year_end_day",
    "Mes_Encerramento_Exercicio_Social": "fiscal_year_end_month",
    "Data_Alteracao_Exercicio_Social": "fiscal_year_changed_on",
    "Pagina_Web": None,
}
VALOR: dict[str, str | None] = {
    **_KEY,
    "Valor_Mobiliario": "security_type",
    "Sigla_Classe_Acao_Preferencial": "preferred_class_code",
    "Classe_Acao_Preferencial": "preferred_class",
    "Codigo_Negociacao": "trading_code",
    "Composicao_BDR_Unit": "composition",
    "Mercado": "market",
    "Sigla_Entidade_Administradora": "operator_code",
    "Entidade_Administradora": "operator_name",
    "Data_Inicio_Negociacao": "trading_start",
    "Data_Fim_Negociacao": "trading_end",
    "Segmento": "listing_segment",
    "Data_Inicio_Listagem": "listing_start",
    "Data_Fim_Listagem": "listing_end",
}
INTS = {"version": pl.Int16, "fiscal_year_end_day": pl.Int16, "fiscal_year_end_month": pl.Int16}
KEYS = {"cnpj", "reference_date", "version", "doc_id"}
_DATE_NAMES = {
    "reference_date",
    "received_on",
    "incorporated_on",
    "registered_on",
    "trading_start",
    "trading_end",
    "listing_start",
    "listing_end",
    "fiscal_year_changed_on",
}


def _is_date(v: str) -> bool:
    return v in _DATE_NAMES or v.endswith("_since")


class LayoutError(ValueError):
    pass


def _dtype(v: str) -> Any:
    return pl.Date if _is_date(v) else INTS.get(v, pl.String)


def _unit(v: str) -> str:
    return "date" if _is_date(v) else ("count" if v in INTS else "")


def _contract(table: str, desc: str, cols: dict[str, str | None]) -> Contract:
    return Contract(
        table=f"staging.cvm_fca.{table}",
        version=1,
        description=desc,
        columns=tuple(
            Column(
                v,
                _dtype(v),
                f"{k} as written" + ("; a ticker, a wildcard or free text" if v == "trading_code" else ""),
                k.lower(),
                _unit(v),
                nullable=v not in KEYS,
            )
            for k, v in cols.items()
            if v is not None
        ),
    )


DOCUMENT = _contract(
    "document", "An FCA version as CVM's yearly index lists it (delivery date = knowledge time).", INDEX
)
COMPANY = _contract("company", "Company identity, registration and controller data of the latest FCA version.", GERAL)
SECURITY = _contract(
    "security",
    "A security of the company with its trading code, market, segment and dates (latest FCA version).",
    VALOR,
)
CONTRACTS = {"document": DOCUMENT, "company": COMPANY, "security": SECURITY}


def _cast(k: str, v: str) -> pl.Expr:
    c = pl.col(k).str.strip_chars()
    if _is_date(v):
        return c.str.strptime(pl.Date, "%Y-%m-%d", strict=False).alias(v)
    if v in INTS:
        return c.cast(INTS[v], strict=False).alias(v)
    return pl.col(k).alias(v)


def parse_member(data: bytes, name: str, cols: dict[str, str | None], row: dict[str, Any]) -> pl.DataFrame:
    text = data.decode("cp1252", errors="replace")  # cp1252 leaves five bytes undefined; none seen in FCA
    head = text.split("\n", 1)[0].rstrip("\r").split(";")
    if head != list(cols):
        raise LayoutError(f"FCA {name}: header changed: {head}")
    df = pl.read_csv(io.StringIO(text), separator=";", infer_schema=False, quote_char=None)
    kept = {k: v for k, v in cols.items() if v is not None}
    out = df.with_row_index("i", offset=2).select(
        *[_cast(k, v) for k, v in kept.items()],
        pl.lit(row["raw_sha256"]).alias("raw_sha256"),
        (pl.lit(f"member={name};line=") + pl.col("i").cast(pl.String)).alias("raw_locator"),
        pl.lit(row["ingest_run_id"]).alias("ingest_run_id"),
    )
    for k, v in kept.items():
        if v in INTS or _is_date(v):
            lost = int((df[k].str.strip_chars().str.len_chars() > 0).sum() - out[v].drop_nulls().len())
            if lost:
                raise LayoutError(f"FCA {name}: {lost} values of {k} do not cast to {_dtype(v)}")
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
        m = re.fullmatch(r"fca_cia_aberta_(?:(geral|valor_mobiliario)_)?(\d{4})\.csv", name)
        if not m:
            continue  # members not parsed (see the module docstring)
        part = f"year={m.group(2)}"
        if m.group(1) == "geral":
            yield Parsed("company", part, parse_member(data, name, GERAL, row))
        elif m.group(1):
            yield Parsed("security", part, parse_member(data, name, VALOR, row))
        else:
            yield Parsed("document", part, parse_member(data, name, INDEX, row))
