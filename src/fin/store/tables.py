"""Parquet in the rebuildable zones: zstd, row groups sized for DuckDB scans, atomic replace (PLAN §4.2)."""

from __future__ import annotations

import os
from pathlib import Path

import polars as pl

ROW_GROUP = 500_000


def write_parquet(df: pl.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".tmp-{path.name}")
    df.write_parquet(tmp, compression="zstd", row_group_size=ROW_GROUP, statistics=True)
    os.replace(tmp, path)
    return path


def read_parquet_dir(directory: Path) -> pl.DataFrame | None:
    files = sorted(p for p in directory.rglob("*.parquet") if not p.name.startswith(".tmp-"))
    if not files:
        return None
    return pl.read_parquet(files, hive_partitioning=False)
