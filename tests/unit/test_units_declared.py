"""Invariant 8: every numeric column of every contract states its unit (currency, scale, ratio, count…)."""

from __future__ import annotations

import importlib
import pkgutil

import polars as pl

import fin
from fin.schema import Contract

NUMERIC = (pl.Int8, pl.Int16, pl.Int32, pl.Int64, pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64, pl.Float32,
           pl.Float64, pl.Decimal)  # fmt: skip


def _contracts() -> list[Contract]:
    found: dict[str, Contract] = {}
    for m in pkgutil.walk_packages(fin.__path__, "fin."):
        mod = importlib.import_module(m.name)
        for v in vars(mod).values():
            if isinstance(v, Contract):
                found[v.table] = v
            elif isinstance(v, dict):
                for w in v.values():  # CONTRACTS dicts
                    if isinstance(w, Contract):
                        found[w.table] = w
    return list(found.values())


def _numeric(dtype: object) -> bool:
    base = dtype if isinstance(dtype, type) else type(dtype)
    return any(base is n or (isinstance(n, type) and issubclass(base, n)) for n in NUMERIC)


# integers that are identifiers or codes, not quantities (schema.Column: "" only for identifiers and labels)
IDENTIFIERS = {
    "version": "filing/report version number",
    "doc_id": "document id at the source",
    "selic_code": "Selic code of a bond",
    "series_id": "a source's series code",
    "tpmerc": "B3 market-type code",
    "strike_correction": "B3 correction-index code",
    "meeting": "Copom meeting number",
    "block": "CDA block number",
    "base": "Focus base-calculation code",
}


def test_every_numeric_column_has_a_unit() -> None:
    contracts = _contracts()
    assert len(contracts) > 50
    missing = [
        f"{c.table}.{col.name}"
        for c in contracts
        for col in c.columns
        if _numeric(col.dtype) and not col.unit and col.name not in IDENTIFIERS
    ]
    assert not missing, f"{len(missing)} numeric columns without a unit: {missing[:40]}"
