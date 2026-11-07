"""CVM DFP (annual) and ITR (quarterly) statement zips -> staging `statement_line`, `document`, `share_capital`
(docs/sources/cvm_dfp_itr.md).

Source-shaped. One zip is a year of one form; its members are the index of delivered documents (`document`), one CSV
per statement and consolidation (`statement_line`) and the share counts (`share_capital`). The auditor's report
(`parecer`, free text) stays in raw.

- `value` is VL_CONTA exactly as written, in `currency` × `scale` (MIL = thousands): the scale is applied by the core
  step that maps accounts to facts (PLAN §4.3.6), never here.
- The statement members hold only the latest version of each filing; `document` lists every version delivered with
  its date (DT_RECEB, the knowledge date). Each weekly zip archived is a snapshot (restatements stay visible).

Layout measured 2026-11-07 on all 33 zips (DFP 2010–2026, ITR 2011–2026): one header per member kind, identical in
every year; cp1252; `;`; dates ISO.
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

VALUE = pl.Decimal(38, 10)  # VL_CONTA carries 9-10 decimals (measured)
STATEMENTS = ("BPA", "BPP", "DRE", "DRA", "DFC_MI", "DFC_MD", "DMPL", "DVA")
_MEMBER = re.compile(r"^(dfp|itr)_cia_aberta(?:_(?P<kind>[A-Za-z_]+?))?_(?P<year>\d{4})\.csv$")

LINE_HEADER = [
    "CNPJ_CIA",
    "DT_REFER",
    "VERSAO",
    "DENOM_CIA",
    "CD_CVM",
    "GRUPO_DFP",
    "MOEDA",
    "ESCALA_MOEDA",
    "ORDEM_EXERC",
    "DT_INI_EXERC",
    "DT_FIM_EXERC",
    "COLUNA_DF",
    "CD_CONTA",
    "DS_CONTA",
    "VL_CONTA",
    "ST_CONTA_FIXA",
]
INDEX_HEADER = [
    "CNPJ_CIA",
    "DT_REFER",
    "VERSAO",
    "DENOM_CIA",
    "CD_CVM",
    "CATEG_DOC",
    "ID_DOC",
    "DT_RECEB",
    "LINK_DOC",
]
CAPITAL_HEADER = [
    "CNPJ_CIA",
    "DT_REFER",
    "VERSAO",
    "DENOM_CIA",
    "QT_ACAO_ORDIN_CAP_INTEGR",
    "QT_ACAO_PREF_CAP_INTEGR",
    "QT_ACAO_TOTAL_CAP_INTEGR",
    "QT_ACAO_ORDIN_TESOURO",
    "QT_ACAO_PREF_TESOURO",
    "QT_ACAO_TOTAL_TESOURO",
]


class LayoutError(ValueError):
    pass


_COMPANY = (
    Column("form", pl.String, "dfp (annual) or itr (quarterly)", "formulário", nullable=False),
    Column("cnpj", pl.String, "CNPJ_CIA as written (00.000.000/0001-91)", "CNPJ da companhia", nullable=False),
    Column(
        "reference_date",
        pl.Date,
        "DT_REFER: the period the document reports",
        "data de referência",
        "date",
        nullable=False,
    ),
    Column(
        "version",
        pl.Int16,
        "VERSAO: 1 for the first delivery, +1 per re-presentation",
        "versão",
        "count",
        nullable=False,
    ),
    Column("company_name", pl.String, "DENOM_CIA as written; not an identifier", "denominação"),
)

STATEMENT_LINE = Contract(
    table="staging.cvm_dfp_itr.statement_line",
    version=1,
    description="One account line of one statement of one filing, as CVM's open-data CSV gives it.",
    columns=(
        *_COMPANY,
        Column("cd_cvm", pl.String, "CD_CVM, 6 digits", "código CVM", nullable=False),
        Column(
            "statement", pl.String, "BPA, BPP, DRE, DRA, DFC_MI, DFC_MD, DMPL or DVA", "demonstração", nullable=False
        ),
        Column("consolidation", pl.String, "con (consolidated) or ind (individual)", "consolidação", nullable=False),
        Column("statement_group", pl.String, "GRUPO_DFP as written", "grupo DFP"),
        Column("currency", pl.String, "MOEDA (REAL)", "moeda", nullable=False),
        Column("scale", pl.String, "ESCALA_MOEDA: MIL (thousands) or UNIDADE", "escala", nullable=False),
        Column(
            "period_order",
            pl.String,
            "ORDEM_EXERC: ÚLTIMO (this period) or PENÚLTIMO (the prior, as restated)",
            "ordem do exercício",
            nullable=False,
        ),
        Column(
            "period_start", pl.Date, "DT_INI_EXERC (flows: DRE, DFC, DMPL, DRA, DVA)", "início do exercício", "date"
        ),
        Column("period_end", pl.Date, "DT_FIM_EXERC", "fim do exercício", "date", nullable=False),
        Column("equity_column", pl.String, "COLUNA_DF (DMPL only): the equity component", "coluna da DMPL"),
        Column(
            "account_code",
            pl.String,
            "CD_CONTA (1, 1.01, 3.99.01.01…); meaning differs by sector",
            "código da conta",
            nullable=False,
        ),
        Column("account_name", pl.String, "DS_CONTA as written", "descrição da conta"),
        Column("value", VALUE, "VL_CONTA as written", "valor", "`currency` × `scale`", nullable=False),
        Column(
            "fixed_account", pl.Boolean, "ST_CONTA_FIXA: S = a fixed CVM account, N = the company's own", "conta fixa"
        ),
    ),
    rules=(
        Rule("statement_known", pl.col("statement").is_in(STATEMENTS)),
        Rule("currency_real", pl.col("currency") == "REAL"),
        Rule("scale_known", pl.col("scale").is_in(["MIL", "UNIDADE"])),
        Rule("period_order_known", pl.col("period_order").is_in(["ÚLTIMO", "PENÚLTIMO"])),
        Rule("period_ordered", pl.col("period_start").is_null() | (pl.col("period_start") <= pl.col("period_end"))),
    ),
)

DOCUMENT = Contract(
    table="staging.cvm_dfp_itr.document",
    version=1,
    description="Every version of every DFP/ITR delivered, with its delivery date (the knowledge date).",
    columns=(
        *_COMPANY,
        Column("cd_cvm", pl.String, "CD_CVM, 6 digits", "código CVM", nullable=False),
        Column("category", pl.String, "CATEG_DOC (DFP, ITR)", "categoria"),
        Column("doc_id", pl.Int64, "ID_DOC", "id do documento", nullable=False),
        Column(
            "received_on", pl.Date, "DT_RECEB: delivery date (date only)", "data de recebimento", "date", nullable=False
        ),
        Column("link", pl.String, "LINK_DOC", "link"),
    ),
)

SHARE_CAPITAL = Contract(
    table="staging.cvm_dfp_itr.share_capital",
    version=1,
    description="Shares paid in and held in treasury per filing (composicao_capital).",
    columns=(
        *_COMPANY,
        *(
            Column(f"{a}_{b}", pl.Int64, f"QT_ACAO_{s}_{t}", f"ações {s.lower()} {t.lower()}", "shares")
            for a, s in (("common", "ORDIN"), ("preferred", "PREF"), ("total", "TOTAL"))
            for b, t in (("paid_in", "CAP_INTEGR"), ("treasury", "TESOURO"))
        ),
    ),
    rules=(Rule("counts_non_negative", pl.min_horizontal(pl.col(r"^(common|preferred|total)_.*$")) >= 0),),
)

CONTRACTS = {"statement_line": STATEMENT_LINE, "document": DOCUMENT, "share_capital": SHARE_CAPITAL}


def _read(z: zipfile.ZipFile, name: str, header: list[str] | None) -> pl.DataFrame:
    text = z.read(name).decode("cp1252")
    first = text.split("\n", 1)[0].rstrip("\r").split(";")
    if header is not None and any(c not in header for c in first):
        raise LayoutError(f"{name}: unknown columns {[c for c in first if c not in header]}")
    return pl.read_csv(io.StringIO(text), separator=";", infer_schema=False, quote_char=None)


def _provenance(df: pl.DataFrame, name: str, row: dict[str, Any]) -> list[pl.Expr]:
    return [
        pl.lit(row["raw_sha256"]).alias("raw_sha256"),
        (pl.lit(f"member={name};line=") + (pl.int_range(2, df.height + 2)).cast(pl.String)).alias("raw_locator"),
        pl.lit(row["ingest_run_id"]).alias("ingest_run_id"),
    ]


def _day(col: str) -> pl.Expr:
    return pl.col(col).str.strptime(pl.Date, "%Y-%m-%d")


def _company(form: str) -> list[pl.Expr]:
    return [
        pl.lit(form).alias("form"),
        pl.col("CNPJ_CIA").alias("cnpj"),
        _day("DT_REFER").alias("reference_date"),
        pl.col("VERSAO").cast(pl.Int16).alias("version"),
        pl.col("DENOM_CIA").alias("company_name"),
    ]


def parse_lines(df: pl.DataFrame, form: str, statement: str, consolidation: str) -> list[pl.Expr]:
    finest = df["VL_CONTA"].str.extract(r"\.(\d+)$").str.len_chars().max()
    if finest is not None and int(finest) > VALUE.scale:  # type: ignore[arg-type]
        raise LayoutError(f"VL_CONTA with {finest} decimals; a cast would round")

    def opt(c: str) -> pl.Expr:
        return pl.col(c) if c in df.columns else pl.lit(None, dtype=pl.String)

    return [
        *_company(form),
        pl.col("CD_CVM").alias("cd_cvm"),
        pl.lit(statement).alias("statement"),
        pl.lit(consolidation).alias("consolidation"),
        pl.col("GRUPO_DFP").alias("statement_group"),
        pl.col("MOEDA").alias("currency"),
        pl.col("ESCALA_MOEDA").alias("scale"),
        pl.col("ORDEM_EXERC").alias("period_order"),
        opt("DT_INI_EXERC").str.strptime(pl.Date, "%Y-%m-%d").alias("period_start"),
        _day("DT_FIM_EXERC").alias("period_end"),
        opt("COLUNA_DF").alias("equity_column"),
        pl.col("CD_CONTA").alias("account_code"),
        pl.col("DS_CONTA").alias("account_name"),
        pl.col("VL_CONTA").cast(VALUE).alias("value"),
        pl.col("ST_CONTA_FIXA").replace_strict({"S": True, "N": False}, default=None).alias("fixed_account"),
    ]


def parse_zip(blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
    z = zipfile.ZipFile(io.BytesIO(blob))
    for name in z.namelist():
        m = _MEMBER.match(name)
        if m is None:
            raise LayoutError(f"unexpected member {name}")
        form, kind, year = m.group(1), m.group("kind"), m.group("year")
        part = f"form={form}/year={year}"
        if kind is None:
            df = _read(z, name, INDEX_HEADER)
            out = df.select(
                *_company(form),
                pl.col("CD_CVM").alias("cd_cvm"),
                pl.col("CATEG_DOC").alias("category"),
                pl.col("ID_DOC").cast(pl.Int64).alias("doc_id"),
                _day("DT_RECEB").alias("received_on"),
                pl.col("LINK_DOC").alias("link"),
                *_provenance(df, name, row),
            )
            yield Parsed("document", part, out)
        elif kind == "composicao_capital":
            df = _read(z, name, CAPITAL_HEADER)
            counts = [
                pl.col(f"QT_ACAO_{s}_{t}").cast(pl.Int64).alias(f"{a}_{b}")
                for a, s in (("common", "ORDIN"), ("preferred", "PREF"), ("total", "TOTAL"))
                for b, t in (("paid_in", "CAP_INTEGR"), ("treasury", "TESOURO"))
            ]
            yield Parsed("share_capital", part, df.select(*_company(form), *counts, *_provenance(df, name, row)))
        elif kind == "parecer":
            continue  # the auditor's report: free text, kept in raw
        else:
            statement, _, consolidation = kind.rpartition("_")
            if statement not in STATEMENTS or consolidation not in ("con", "ind"):
                raise LayoutError(f"unexpected statement member {name}")
            df = _read(z, name, LINE_HEADER)
            out = df.select(*parse_lines(df, form, statement, consolidation), *_provenance(df, name, row))
            yield Parsed("statement_line", f"{part}/statement={statement}_{consolidation}", out)
