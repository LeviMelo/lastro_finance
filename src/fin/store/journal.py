"""Append-only tables written as one Parquet part per ingest run.

During a run, rows are appended to `<dir>/_journal/<run_id>.jsonl` and fsynced one by one, so a crash loses nothing
that was acknowledged. Sealing a run writes `<dir>/part-<run_id>.parquet` with the table's fixed schema and removes
the journal. `recover()` seals journals left by runs that died. Readers see sealed parts and live journals alike.
Parts are never rewritten.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from pathlib import Path
from typing import Any

import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq


def _default(o: object) -> str:
    if isinstance(o, datetime | date):
        return o.isoformat()
    raise TypeError(f"not JSON-serializable: {type(o).__name__}")


class Journal:
    def __init__(self, directory: Path, schema: pa.Schema) -> None:
        self.dir = directory
        self.schema = schema
        self._journals = directory / "_journal"

    def append(self, run_id: str, row: Mapping[str, Any]) -> None:
        unknown = set(row) - set(self.schema.names)
        if unknown:
            raise KeyError(f"{self.dir.name}: columns not in schema: {sorted(unknown)}")
        self._journals.mkdir(parents=True, exist_ok=True)
        line = json.dumps(row, default=_default, ensure_ascii=False, sort_keys=True)
        with (self._journals / f"{run_id}.jsonl").open("a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())

    def seal(self, run_id: str) -> Path | None:
        src = self._journals / f"{run_id}.jsonl"
        if not src.exists():
            return None
        table = self._to_table(self._read_jsonl(src))
        dst = self.dir / f"part-{run_id}.parquet"
        tmp = dst.with_suffix(".parquet.tmp")
        pq.write_table(table, tmp, compression="zstd")
        os.replace(tmp, dst)
        src.unlink()
        return dst

    def recover(self) -> list[str]:
        """Seal every journal left behind by a run that did not close. Returns their run ids."""
        if not self._journals.exists():
            return []
        ids = sorted(p.stem for p in self._journals.glob("*.jsonl"))
        for run_id in ids:
            self.seal(run_id)
        return ids

    def read(self) -> pl.DataFrame:
        tables = [pq.read_table(p, schema=self.schema) for p in sorted(self.dir.glob("part-*.parquet"))]
        if self._journals.exists():
            for p in sorted(self._journals.glob("*.jsonl")):
                tables.append(self._to_table(self._read_jsonl(p)))
        if not tables:
            return pl.from_arrow(self.schema.empty_table())  # type: ignore[return-value]
        return pl.from_arrow(pa.concat_tables(tables))  # type: ignore[return-value]

    @staticmethod
    def _read_jsonl(path: Path) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        with path.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
        return rows

    def _to_table(self, rows: Iterable[dict[str, Any]]) -> pa.Table:
        cols: dict[str, list[Any]] = {n: [] for n in self.schema.names}
        for r in rows:
            for n in self.schema.names:
                cols[n].append(r.get(n))
        arrays = []
        for field in self.schema:
            values = cols[field.name]
            if pa.types.is_timestamp(field.type):
                values = [datetime.fromisoformat(v) if isinstance(v, str) else v for v in values]
            elif pa.types.is_date(field.type):
                values = [date.fromisoformat(v) if isinstance(v, str) else v for v in values]
            arrays.append(pa.array(values, type=field.type))
        return pa.Table.from_arrays(arrays, schema=self.schema)
