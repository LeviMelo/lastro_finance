"""BCB Copom decision history (`/api/servico/sitebcb/historicotaxasjuros`) -> staging `decision`.

One row per rate decision, as served: a meeting can carry several (meeting 33, 1999: three, the later two by the
president's use of the bias, `UsoMetaSelic`). `target` is `MetaSelic` as written: the Selic target in % a.a. from
1999-03-05; before that the field holds the TBC (19-29 in 1998, 1.9 in 1996), whose unit is not stated
(docs/sources/context_br.md). The Selic target series from 1999 is SGS 432.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from typing import Any

import polars as pl

from fin.ingest.base import Parsed
from fin.schema import Column, Contract

RATE = pl.Decimal(18, 6)

DECISION = Contract(
    table="staging.bcb_copom.decision",
    version=1,
    description="A Copom rate decision with its validity period, as BCB's history serves it.",
    columns=(
        Column("meeting", pl.Int32, "NumeroReuniaoCopom", "reunião", nullable=False),
        Column("extraordinary", pl.Boolean, "ReuniaoExtraordinaria", "extraordinária"),
        Column("meeting_date", pl.Date, "DataReuniaoCopom (Brasília date)", "data da reunião", "date", nullable=False),
        Column("effective_from", pl.Date, "DataInicioVigencia", "início da vigência", "date", nullable=False),
        Column("effective_to", pl.Date, "DataFimVigencia; null while in force", "fim da vigência", "date"),
        Column("bias", pl.String, "Vies (n/a, alta, baixa…)", "viés"),
        Column(
            "used_bias", pl.Boolean, "UsoMetaSelic: a change made by the president's use of the bias", "uso do viés"
        ),
        Column(
            "target",
            RATE,
            "MetaSelic as written (Selic target % a.a. from 1999-03-05; TBC before)",
            "meta",
            "% (see description)",
        ),
        Column("tban", RATE, "TaxaTban (until 1999)", "TBAN", "% a.a."),
        Column(
            "selic_period",
            RATE,
            "TaxaSelicEfetivaVigencia: effective Selic over the period",
            "Selic no período",
            "% over the period",
        ),
        Column("selic_annualized", RATE, "TaxaSelicEfetivaAnualizada", "Selic anualizada", "% a.a."),
        Column("monocratic", pl.Boolean, "descisaoMonocraticaPres (as spelled)", "decisão monocrática"),
    ),
    key=("meeting", "effective_from"),
)
CONTRACTS = {"decision": DECISION}


def _day(v: str | None) -> date | None:
    return date.fromisoformat(v[:10]) if v else None


def _rate(v: Any) -> Decimal | None:
    return None if v is None else Decimal(repr(float(v)))


def parse_decisions(blob: bytes, row: dict[str, Any]) -> pl.DataFrame:
    rows = [
        {
            "meeting": int(r["NumeroReuniaoCopom"]),
            "extraordinary": r.get("ReuniaoExtraordinaria"),
            "meeting_date": _day(r.get("DataReuniaoCopom")),
            "effective_from": _day(r.get("DataInicioVigencia")),
            "effective_to": _day(r.get("DataFimVigencia")),
            "bias": r.get("Vies"),
            "used_bias": r.get("UsoMetaSelic"),
            "target": _rate(r.get("MetaSelic")),
            "tban": _rate(r.get("TaxaTban")),
            "selic_period": _rate(r.get("TaxaSelicEfetivaVigencia")),
            "selic_annualized": _rate(r.get("TaxaSelicEfetivaAnualizada")),
            "monocratic": r.get("descisaoMonocraticaPres"),
            "raw_locator": f"$.conteudo[{i}]",
        }
        for i, r in enumerate(json.loads(blob)["conteudo"])
    ]
    schema = {c.name: c.dtype for c in DECISION.columns} | {"raw_locator": pl.String}
    return pl.DataFrame(rows, schema=schema, orient="row").with_columns(
        pl.lit(row["raw_sha256"]).alias("raw_sha256"), pl.lit(row["ingest_run_id"]).alias("ingest_run_id")
    )


def parse_payload(blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
    yield Parsed("decision", "all", parse_decisions(blob, row))
