"""BCB Focus market expectations (Olinda OData) -> staging `expectation` (docs/sources/context_br.md, bcb_focus).

Eight tables (annual, monthly, quarterly, 12- and 24-month inflation, Selic per Copom meeting, and the Top-5
annual and Selic rankings) share one shape: an indicator, the survey date, a reference period and the distribution of
answers. One staging table holds them all, source-shaped:
- `reference` is the period as written: `2026` (annual), `12/2026` (monthly), `1/2024` (quarter), `R8/2027` (Copom
  meeting) or `12m`/`24m` for the rolling inflation tables;
- statistics are exact decimals of the JSON numbers (shortest round-trip form);
- key casing differs by table (`Indicador` / `indicador`); both are read.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from typing import Any

import polars as pl

from fin.ingest.base import Parsed
from fin.schema import Column, Contract, Rule

STAT = pl.Decimal(38, 12)
HORIZON = {"expectativasmercadoinflacao12meses": "12m", "expectativasmercadoinflacao24meses": "24m"}


class LayoutError(ValueError):
    pass


EXPECTATION = Contract(
    table="staging.bcb_focus.expectation",
    version=1,
    description="One Focus statistic set: an indicator's expected value for a reference period, on a survey date.",
    columns=(
        Column("focus_table", pl.String, "Olinda entity, lower-case", "tabela", nullable=False),
        Column(
            "indicator",
            pl.String,
            "Indicador as written (IPCA, Selic, Câmbio, PIB Total…)",
            "indicador",
            nullable=False,
        ),
        Column("indicator_detail", pl.String, "IndicadorDetalhe (annual table)", "detalhe"),
        Column("survey_date", pl.Date, "Data: the date of the statistics", "data", "date", nullable=False),
        Column(
            "reference",
            pl.String,
            "period expected (2026, 12/2026, 1/2024, R8/2027, 12m, 24m)",
            "referência",
            nullable=False,
        ),
        Column("calc_type", pl.String, "tipoCalculo (Top 5: C short, M medium, L long)", "tipo de cálculo"),
        Column("smoothed", pl.String, "Suavizada (S/N, 12- and 24-month inflation)", "suavizada"),
        Column("base", pl.Int16, "baseCalculo: 0 = last 30 days, 1 = last 5 business days", "base de cálculo"),
        Column("mean", STAT, "Media", "média", "indicator unit"),
        Column("median", STAT, "Mediana", "mediana", "indicator unit"),
        Column("std", STAT, "DesvioPadrao", "desvio padrão", "indicator unit"),
        Column("minimum", STAT, "Minimo", "mínimo", "indicator unit"),
        Column("maximum", STAT, "Maximo", "máximo", "indicator unit"),
        Column("cv", STAT, "coeficienteVariacao (Top 5 Selic)", "coeficiente de variação", "ratio"),
        Column("respondents", pl.Int32, "numeroRespondentes", "respondentes", "count"),
    ),
    rules=(Rule("has_median_or_mean", pl.col("median").is_not_null() | pl.col("mean").is_not_null()),),
)

CONTRACTS = {"expectation": EXPECTATION}


def _get(r: dict[str, Any], *keys: str) -> Any:
    for k in keys:
        if k in r:
            return r[k]
        lk = k[0].lower() + k[1:]
        if lk in r:
            return r[lk]
    return None


def _num(v: Any) -> str | None:
    return None if v is None else format(Decimal(repr(float(v))), "f")


def parse_expectations(blob: bytes, row: dict[str, Any]) -> pl.DataFrame:
    table = str(row["dataset_id"])
    doc = json.loads(blob)
    if "value" not in doc:
        raise LayoutError(f"Focus {table}: no 'value' array")
    out: list[dict[str, Any]] = []
    for i, r in enumerate(doc["value"]):
        ref = _get(r, "DataReferencia", "Reuniao") or HORIZON.get(table)
        if ref is None:
            raise LayoutError(f"Focus {table}: row {i} has no reference period: {sorted(r)}")
        base = _get(r, "baseCalculo")
        resp = _get(r, "numeroRespondentes")
        out.append(
            {
                "focus_table": table,
                "indicator": _get(r, "Indicador"),
                "indicator_detail": _get(r, "IndicadorDetalhe"),
                "survey_date": date.fromisoformat(str(_get(r, "Data"))[:10]),
                "reference": str(ref),
                "calc_type": _get(r, "tipoCalculo"),
                "smoothed": _get(r, "Suavizada"),
                "base": None if base is None else int(base),
                "mean": _num(_get(r, "Media")),
                "median": _num(_get(r, "Mediana")),
                "std": _num(_get(r, "DesvioPadrao")),
                "minimum": _num(_get(r, "Minimo")),
                "maximum": _num(_get(r, "Maximo")),
                "cv": _num(_get(r, "coeficienteVariacao")),
                "respondents": None if resp is None else int(resp),
                "raw_locator": f"$.value[{i}]",
            }
        )
    stats = ("mean", "median", "std", "minimum", "maximum", "cv")
    schema = {c.name: (pl.String if c.name in stats else c.dtype) for c in EXPECTATION.columns} | {
        "raw_locator": pl.String
    }
    df = pl.DataFrame(out, schema=schema, orient="row")
    return df.with_columns(
        *[pl.col(c).cast(STAT) for c in stats],
        pl.lit(row["raw_sha256"]).alias("raw_sha256"),
        pl.lit(row["ingest_run_id"]).alias("ingest_run_id"),
    )


def parse_payload(blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
    yield Parsed("expectation", str(row["dataset_id"]), parse_expectations(blob, row))
