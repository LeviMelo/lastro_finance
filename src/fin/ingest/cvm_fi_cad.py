"""CVM fund register (FI/CAD) -> staging `fund`, `fund_history`, `registered_fund`, `registered_class`,
`registered_subclass` (docs/sources/cvm_fi_cadastro.md, ADR-0025).

Two generations of register, both archived whole and daily:
- legacy (pre CVM Res. 175), keyed by fund CNPJ: `cad_fi.csv` -> `fund`, one row per registration (CD_CVM) of a CNPJ;
  `cad_fi_hist.zip` -> `fund_history`, the dated attribute changes in long form (attribute, value, valid_from/to).
- CVM 175, `registro_fundo_classe.zip`: `registro_fundo.csv` -> `registered_fund` (ID_Registro_Fundo, CNPJ_Fundo,
  Data_Adaptacao_RCVM175), `registro_classe.csv` -> `registered_class` (ID_Registro_Classe -> ID_Registro_Fundo,
  CNPJ_Classe), `registro_subclasse.csv` -> `registered_subclass` (ID_Subclasse -> ID_Registro_Classe).

Only companies are read. Never parsed: the responsible director (`DIRETOR`/`Diretor`), the individuals who manage a
fund (a manager with `PF` person type loses its name and CPF; the PJ ones keep CNPJ and name), and the controller and
auditor columns (a controller can be a person). CNPJs are stored as 14 digits, punctuation removed.
cp1252, `;`, CRLF, a few stray `"` (no quoting), header checked.
"""

from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import polars as pl

from fin.ingest.base import Parsed
from fin.schema import Column, Contract, Rule


class LayoutError(ValueError):
    pass


@dataclass(frozen=True)
class F:
    src: str
    name: str
    kind: str = "str"  # str | date | brl | cnpj | int
    pj_only: str = ""  # the column holding PF/PJ: a value from a PF row is dropped
    required: bool = False


def _fields_legacy() -> tuple[F, ...]:
    return (
        F("TP_FUNDO", "fund_type"),
        F("CNPJ_FUNDO", "cnpj", "cnpj", required=True),
        F("DENOM_SOCIAL", "name"),
        F("DT_REG", "registered_on", "date"),
        F("DT_CONST", "incorporated_on", "date"),
        F("CD_CVM", "cd_cvm"),
        F("DT_CANCEL", "cancelled_on", "date"),
        F("SIT", "status"),
        F("DT_INI_SIT", "status_since", "date"),
        F("DT_INI_ATIV", "started_on", "date"),
        F("CLASSE", "category"),
        F("DT_INI_CLASSE", "category_since", "date"),
        F("CONDOM", "condominium"),
        F("FUNDO_COTAS", "fund_of_funds"),
        F("FUNDO_EXCLUSIVO", "exclusive"),
        F("TRIB_LPRAZO", "long_term_tax"),
        F("PUBLICO_ALVO", "target_audience"),
        F("ENTID_INVEST", "investment_entity"),
        F("VL_PATRIM_LIQ", "net_assets_brl", "brl"),
        F("DT_PATRIM_LIQ", "net_assets_date", "date"),
        F("CNPJ_ADMIN", "administrator_cnpj", "cnpj"),
        F("ADMIN", "administrator"),
        F("PF_PJ_GESTOR", "manager_person_type"),
        F("CPF_CNPJ_GESTOR", "manager_cnpj", "cnpj", "PF_PJ_GESTOR"),
        F("GESTOR", "manager", "str", "PF_PJ_GESTOR"),
        F("CNPJ_CUSTODIANTE", "custodian_cnpj", "cnpj"),
        F("CUSTODIANTE", "custodian"),
        F("INVEST_CEMPR_EXTER", "foreign_investment"),
        F("CLASSE_ANBIMA", "anbima_class"),
    )


def _fields_fund() -> tuple[F, ...]:
    return (
        F("ID_Registro_Fundo", "fund_id", required=True),
        F("CNPJ_Fundo", "cnpj", "cnpj", required=True),
        F("Codigo_CVM", "cd_cvm"),
        F("Data_Registro", "registered_on", "date"),
        F("Data_Constituicao", "incorporated_on", "date"),
        F("Tipo_Fundo", "fund_type"),
        F("Denominacao_Social", "name"),
        F("Data_Cancelamento", "cancelled_on", "date"),
        F("Situacao", "status"),
        F("Data_Inicio_Situacao", "status_since", "date"),
        F("Data_Adaptacao_RCVM175", "adapted_on", "date"),
        F("Patrimonio_Liquido", "net_assets_brl", "brl"),
        F("Data_Patrimonio_Liquido", "net_assets_date", "date"),
        F("CNPJ_Administrador", "administrator_cnpj", "cnpj"),
        F("Administrador", "administrator"),
        F("Tipo_Pessoa_Gestor", "manager_person_type"),
        F("CPF_CNPJ_Gestor", "manager_cnpj", "cnpj", "Tipo_Pessoa_Gestor"),
        F("Gestor", "manager", "str", "Tipo_Pessoa_Gestor"),
    )


def _fields_class() -> tuple[F, ...]:
    return (
        F("ID_Registro_Fundo", "fund_id", required=True),
        F("ID_Registro_Classe", "class_id", required=True),
        F("CNPJ_Classe", "cnpj", "cnpj", required=True),
        F("Codigo_CVM", "cd_cvm"),
        F("Data_Registro", "registered_on", "date"),
        F("Data_Constituicao", "incorporated_on", "date"),
        F("Data_Inicio", "started_on", "date"),
        F("Tipo_Classe", "class_type"),
        F("Denominacao_Social", "name"),
        F("Situacao", "status"),
        F("Data_Inicio_Situacao", "status_since", "date"),
        F("Classificacao", "category"),
        F("Indicador_Desempenho", "benchmark"),
        F("Classe_Cotas", "quota_class"),
        F("Classificacao_Anbima", "anbima_class"),
        F("Tributacao_Longo_Prazo", "long_term_tax"),
        F("Entidade_Investimento", "investment_entity"),
        F("Permitido_Aplicacao_CemPorCento_Exterior", "foreign_investment"),
        F("Classe_ESG", "esg"),
        F("Forma_Condominio", "condominium"),
        F("Exclusivo", "exclusive"),
        F("Publico_Alvo", "target_audience"),
        F("Patrimonio_Liquido", "net_assets_brl", "brl"),
        F("Data_Patrimonio_Liquido", "net_assets_date", "date"),
        F("CNPJ_Custodiante", "custodian_cnpj", "cnpj"),
        F("Custodiante", "custodian"),
    )


def _fields_subclass() -> tuple[F, ...]:
    return (
        F("ID_Registro_Classe", "class_id", required=True),
        F("ID_Subclasse", "subclass_id", required=True),
        F("Codigo_CVM", "cd_cvm"),
        F("Data_Constituicao", "incorporated_on", "date"),
        F("Data_Inicio", "started_on", "date"),
        F("Denominacao_Social", "name"),
        F("Situacao", "status"),
        F("Data_Inicio_Situacao", "status_since", "date"),
        F("Forma_Condominio", "condominium"),
        F("Exclusivo", "exclusive"),
        F("Publico_Alvo", "target_audience"),
        F("Previdenciario", "pension"),
        F("Exclusivo_INR", "non_resident_only"),
        F("Exclusivo_Previdencia_Complementar", "pension_only"),
    )


FUND, REGISTERED_FUND, REGISTERED_CLASS, REGISTERED_SUBCLASS = (
    _fields_legacy(),
    _fields_fund(),
    _fields_class(),
    _fields_subclass(),
)

# cad_fi_hist members: (attribute, value columns, valid_from column, valid_to column). Companies and plain
# attributes only (no director, manager, controller or auditor members; fees are not parsed).
HIST_MEMBERS: dict[str, tuple[str, tuple[str, ...], str, str]] = {
    "sit": ("status", ("SIT",), "DT_INI_SIT", "DT_FIM_SIT"),
    "classe": ("category", ("CLASSE",), "DT_INI_CLASSE", "DT_FIM_CLASSE"),
    "denom_social": ("name", ("DENOM_SOCIAL",), "DT_INI_DENOM_SOCIAL", "DT_FIM_DENOM_SOCIAL"),
    "denom_comerc": ("trade_name", ("DENOM_COMERC",), "DT_INI_DENOM_COMERC", "DT_FIM_DENOM_COMERC"),
    "condom": ("condominium", ("CONDOM",), "DT_INI_CONDOM", "DT_FIM_CONDOM"),
    "fic": ("fund_of_funds", ("FUNDO_COTAS",), "DT_INI_ST_COTAS", "DT_FIM_ST_COTAS"),
    "exclusivo": ("exclusive", ("FUNDO_EXCLUSIVO",), "DT_INI_ST_EXCLUSIVO", "DT_FIM_ST_EXCLUSIVO"),
    "publico_alvo": ("target_audience", ("PUBLICO_ALVO",), "DT_INI_PUBLICO_ALVO", "DT_FIM_PUBLICO_ALVO"),
    "trib_lprazo": ("long_term_tax", ("TRIB_LPRAZO",), "DT_INI_ST_TRIB_LPRAZO", "DT_FIM_ST_TRIB_LPRAZO"),
    "rentab": ("benchmark", ("RENTAB_FUNDO",), "DT_INI_RENTAB", "DT_FIM_RENTAB"),
    "admin": ("administrator", ("CNPJ_ADMIN", "ADMIN"), "DT_INI_ADMIN", "DT_FIM_ADMIN"),
    "custodiante": ("custodian", ("CNPJ_CUSTODIANTE", "CUSTODIANTE"), "DT_INI_CUSTODIANTE", "DT_FIM_CUSTODIANTE"),
}


def _dtype(k: str) -> Any:
    return {"date": pl.Date, "brl": pl.Decimal(24, 2)}.get(k, pl.String)


def _contract(
    table: str, desc: str, fields: tuple[F, ...], key: tuple[str, ...], rules: tuple[Rule, ...] = ()
) -> Contract:
    return Contract(
        table=f"staging.cvm_fi_cadastro.{table}",
        version=1,
        description=desc,
        columns=tuple(
            Column(
                f.name,
                _dtype(f.kind),
                f"{f.src} as written"
                + ("; 14 digits" if f.kind == "cnpj" else "")
                + ("; PJ rows only" if f.pj_only else ""),
                f.src.lower(),
                {"date": "date", "brl": "BRL"}.get(f.kind, ""),
                nullable=not f.required,
            )
            for f in fields
        ),
        rules=(*(_cnpj_rule(f.name) for f in fields if f.kind == "cnpj"), *rules),
        key=key,
    )


def _cnpj_rule(col: str) -> Rule:
    return Rule(f"{col}_is_14_digits", pl.col(col).str.len_chars().eq(14) | pl.col(col).is_null())


FUND_CONTRACT = _contract(
    "fund", "A legacy (pre CVM 175) fund registration, as cad_fi.csv serves it.", FUND, ("cnpj", "cd_cvm")
)
REG_FUND_CONTRACT = _contract(
    "registered_fund", "A fund of the CVM 175 register (one row per registered manager).", REGISTERED_FUND, ("fund_id",)
)
REG_CLASS_CONTRACT = _contract(
    "registered_class", "A class of the CVM 175 register, linked to its fund.", REGISTERED_CLASS, ("class_id",)
)
REG_SUBCLASS_CONTRACT = _contract(
    "registered_subclass",
    "A subclass of the CVM 175 register, linked to its class.",
    REGISTERED_SUBCLASS,
    ("subclass_id",),
)
HISTORY_CONTRACT = Contract(
    table="staging.cvm_fi_cadastro.fund_history",
    version=1,
    description="One dated value of a legacy fund attribute (cad_fi_hist members), long form.",
    columns=(
        Column("cnpj", pl.String, "CNPJ_FUNDO; 14 digits", "cnpj_fundo", nullable=False),
        Column("registered_on", pl.Date, "DT_REG of the registration the row belongs to", "dt_reg", "date"),
        Column(
            "attribute",
            pl.String,
            "attribute name (status, category, name, administrator...)",
            "atributo",
            nullable=False,
        ),
        Column("value", pl.String, "the value as written", "valor"),
        Column(
            "value_cnpj",
            pl.String,
            "CNPJ of the company named by `value` (administrator, custodian); 14 digits",
            "cnpj do valor",
        ),
        Column("valid_from", pl.Date, "DT_INI_*: first day the value held", "início", "date"),
        Column("valid_to", pl.Date, "DT_FIM_*: day it stopped holding; null while current", "fim", "date"),
    ),
    rules=(
        _cnpj_rule("cnpj"),
        _cnpj_rule("value_cnpj"),
        Rule(
            "valid_to_not_before_from",
            (pl.col("valid_to") >= pl.col("valid_from"))
            | pl.col("valid_to").is_null()
            | pl.col("valid_from").is_null(),
        ),
    ),
)
CONTRACTS = {
    "fund": FUND_CONTRACT,
    "fund_history": HISTORY_CONTRACT,
    "registered_fund": REG_FUND_CONTRACT,
    "registered_class": REG_CLASS_CONTRACT,
    "registered_subclass": REG_SUBCLASS_CONTRACT,
}


def _read(data: bytes, name: str, expect: Iterable[str], exact: bool = True) -> pl.DataFrame:
    text = data.decode("cp1252")
    head = text.split("\n", 1)[0].rstrip("\r").split(";")
    want = list(expect)
    if (head != want) if exact else any(c not in head for c in want):
        raise LayoutError(f"{name}: header changed: {head}")
    return pl.read_csv(io.StringIO(text), separator=";", infer_schema=False, quote_char=None).with_row_index(
        "i", offset=2
    )


def _expr(src: str, kind: str) -> pl.Expr:
    c = pl.col(src).str.strip_chars()
    c = pl.when(c == "").then(None).otherwise(c)
    if kind == "date":
        return c.str.strptime(pl.Date, "%Y-%m-%d", strict=False)
    if kind == "brl":
        return c.cast(pl.Decimal(24, 2), strict=False)
    if kind == "cnpj":
        return c.str.replace_all(r"\D", "")
    return c


def _provenance(name: str, row: dict[str, Any]) -> list[pl.Expr]:
    return [
        pl.lit(row["raw_sha256"]).alias("raw_sha256"),
        (pl.lit(f"member={name};line=") + pl.col("i").cast(pl.String)).alias("raw_locator"),
        pl.lit(row["ingest_run_id"]).alias("ingest_run_id"),
    ]


def parse_table(data: bytes, name: str, fields: tuple[F, ...], row: dict[str, Any]) -> pl.DataFrame:
    df = _read(data, name, [f.src for f in fields], exact=False)
    cols = []
    for f in fields:
        e = _expr(f.src, f.kind)
        if f.pj_only:  # a person's name and CPF are never kept
            e = pl.when(pl.col(f.pj_only).str.strip_chars() == "PJ").then(e).otherwise(None)
        cols.append(e.alias(f.name))
    return df.select(*cols, *_provenance(name, row))


def parse_history(members: dict[str, bytes], row: dict[str, Any]) -> pl.DataFrame:
    frames = []
    for key, (attribute, values, ini, fim) in HIST_MEMBERS.items():
        name = f"cad_fi_hist_{key}.csv"
        if key not in members:
            continue
        df = _read(members[key], name, ["CNPJ_FUNDO", "DT_REG", *values, ini, fim])
        has_cnpj = len(values) == 2
        frames.append(
            df.select(
                _expr("CNPJ_FUNDO", "cnpj").alias("cnpj"),
                _expr("DT_REG", "date").alias("registered_on"),
                pl.lit(attribute).alias("attribute"),
                _expr(values[-1], "str").alias("value"),
                (_expr(values[0], "cnpj") if has_cnpj else pl.lit(None, dtype=pl.String)).alias("value_cnpj"),
                _expr(ini, "date").alias("valid_from"),
                _expr(fim, "date").alias("valid_to"),
                *_provenance(name, row),
            )
        )
    schema = {c.name: c.dtype for c in HISTORY_CONTRACT.all_columns}
    return pl.concat(frames) if frames else pl.DataFrame(schema=schema)


_HIST = re.compile(r"cad_fi_hist_(\w+)\.csv")
_REGISTRO = {
    "registro_fundo.csv": ("registered_fund", REGISTERED_FUND),
    "registro_classe.csv": ("registered_class", REGISTERED_CLASS),
    "registro_subclasse.csv": ("registered_subclass", REGISTERED_SUBCLASS),
}


def parse_payload(blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
    notes = row.get("notes") or ""
    dataset = str(row["dataset_id"])
    if "|" in notes:  # an unpacked member (ADR-0014)
        members = {notes.split("|", 1)[1]: blob}
    elif blob[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            members = {n: z.read(n) for n in z.namelist()}
    elif dataset == "cad_fi":
        members = {"cad_fi.csv": blob}
    else:
        return  # the JSON record of an unpacked zip
    hist: dict[str, bytes] = {}
    for name, data in members.items():
        if name == "cad_fi.csv":
            yield Parsed("fund", "all", parse_table(data, name, FUND, row))
        elif name in _REGISTRO:
            ds, fields = _REGISTRO[name]
            yield Parsed(ds, "all", parse_table(data, name, fields, row))
        elif (m := _HIST.fullmatch(name)) and m.group(1) in HIST_MEMBERS:
            hist[m.group(1)] = data
    if hist:  # one frame per payload: staging holds one file per (dataset, partition, raw object)
        yield Parsed("fund_history", "all", parse_history(hist, row))
