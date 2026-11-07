"""Table contracts: typed columns with unit and meaning, and named row rules (PLAN §4.1 invariants 2, 8, 11; §4.11.1).

A contract is the single declaration of a table. It does three jobs:
- `conform` checks the frame's columns and dtypes exactly; a mismatch is a connector defect and raises.
- `split` applies the row rules; failing rows go to quarantine with the names of the rules they broke, never away.
- the data dictionary is generated from it (`fin dictionary`), so every column states its unit and meaning.

Every staging and core table carries the provenance columns `raw_sha256`, `raw_locator` and `ingest_run_id`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import polars as pl


class ContractError(ValueError):
    """A frame does not have the columns or types its contract declares: a defect in code, not in data."""


@dataclass(frozen=True)
class Column:
    name: str
    dtype: pl.DataType | type[pl.DataType]
    en: str
    pt: str = ""
    unit: str = ""  # e.g. "BRL per share", "% a.a.", "count", "date"; "" only for identifiers and labels
    nullable: bool = True


@dataclass(frozen=True)
class Rule:
    name: str
    valid: pl.Expr  # True where the row satisfies the rule; null counts as a violation


PROVENANCE: tuple[Column, ...] = (
    Column(
        "raw_sha256",
        pl.String,
        "SHA-256 of the raw object the row came from",
        "SHA-256 do objeto bruto",
        nullable=False,
    ),
    Column(
        "raw_locator",
        pl.String,
        "where in the raw object: member, line, JSON path or page",
        "localizador",
        nullable=False,
    ),
    Column("ingest_run_id", pl.String, "the run that fetched the raw object", "execução de ingestão", nullable=False),
)


@dataclass(frozen=True)
class Contract:
    table: str
    version: int
    description: str
    columns: tuple[Column, ...]
    rules: tuple[Rule, ...] = ()
    key: tuple[str, ...] = ()
    provenance: bool = True
    all_columns: tuple[Column, ...] = field(init=False)

    def __post_init__(self) -> None:
        cols = self.columns + (PROVENANCE if self.provenance else ())
        names = [c.name for c in cols]
        if len(names) != len(set(names)):
            raise ContractError(f"{self.table}: duplicate column names")
        object.__setattr__(self, "all_columns", cols)

    @property
    def names(self) -> list[str]:
        return [c.name for c in self.all_columns]

    def schema(self) -> pl.Schema:
        return pl.Schema({c.name: c.dtype for c in self.all_columns})

    def conform(self, df: pl.DataFrame) -> pl.DataFrame:
        missing = [n for n in self.names if n not in df.columns]
        extra = [n for n in df.columns if n not in self.names]
        if missing or extra:
            raise ContractError(f"{self.table} v{self.version}: missing {missing}, unexpected {extra}")
        df = df.select(self.names)
        want = self.schema()
        wrong = [(n, str(df.schema[n]), str(want[n])) for n in self.names if df.schema[n] != want[n]]
        if wrong:
            raise ContractError(f"{self.table} v{self.version}: dtype mismatch (column, got, want) {wrong}")
        return df

    def split(self, df: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
        """(valid rows, quarantined rows with a `reject_rules` list column). Row order is preserved in each."""
        df = self.conform(df)
        checks = [(f"not_null:{c.name}", pl.col(c.name).is_not_null()) for c in self.all_columns if not c.nullable]
        checks += [(r.name, r.valid.fill_null(False)) for r in self.rules]
        if not checks:
            return df, df.clear().with_columns(pl.lit([], dtype=pl.List(pl.String)).alias("reject_rules"))
        reasons = df.select(
            pl.concat_list(
                [pl.when(~ok).then(pl.lit(name)).otherwise(pl.lit(None, dtype=pl.String)) for name, ok in checks]
            )
            .list.drop_nulls()
            .alias("reject_rules")
        )
        tagged = pl.concat([df, reasons], how="horizontal")
        bad = tagged["reject_rules"].list.len() > 0
        return tagged.filter(~bad).drop("reject_rules"), tagged.filter(bad)
