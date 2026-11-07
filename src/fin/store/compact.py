"""Re-encode archived versions of re-sent files as deltas of their previous version (ADR-0014).

A version group is the objects stored for one (source, dataset, locator), in the order they were first fetched.
Each object after the first becomes a delta of the one before it when that pays (see `RawStore`); a chain reaching
`KEYFRAME` leaves the next object whole. What `read` returns never changes: each rewrite is verified first.
"""

from __future__ import annotations

import itertools
from collections import defaultdict
from collections.abc import Callable, Iterable
from pathlib import Path

import polars as pl

from fin.store.raw import RawStore
from fin.store.tables import write_parquet


def version_groups(manifest: pl.DataFrame, sources: Iterable[str] | None = None) -> list[tuple[str, list[str]]]:
    m = manifest.filter(pl.col("http_status") == 200)
    if sources is not None:
        m = m.filter(pl.col("source_id").is_in(list(sources)))
    first = (
        m.group_by("source_id", "dataset_id", "notes", "raw_sha256")
        .agg(pl.col("fetched_at").min())
        .sort("source_id", "dataset_id", "notes", "fetched_at", nulls_last=True)
    )
    out: list[tuple[str, list[str]]] = []
    for (sid, _, _), g in first.group_by("source_id", "dataset_id", "notes", maintain_order=True):
        shas = g["raw_sha256"].to_list()
        if len(shas) > 1:
            out.append((str(sid), shas))
    return out


def compact(
    raw: RawStore,
    manifest: pl.DataFrame,
    sources: Iterable[str] | None = None,
    progress: Callable[[str, int], None] | None = None,
) -> dict[str, int]:
    """Bytes saved per source."""
    saved: dict[str, int] = defaultdict(int)
    for sid, shas in version_groups(manifest, sources):
        for prev, cur in itertools.pairwise(shas):
            n = raw.rewrite_as_delta(cur, prev)
            saved[sid] += n
            if progress is not None and n:
                progress(sid, n)
    return dict(saved)


def compact_staging(root: Path, min_files: int = 20) -> tuple[int, int, int, int]:
    """Merge the per-object Parquet files of each staging partition holding at least `min_files` into one
    `compact-<n>.parquet` (rows keep `raw_sha256`). Returns (files before, files after, bytes before, bytes after).
    A reparse clears the source's staging first, so a compacted file is never loaded twice."""
    files_before = files_after = bytes_before = bytes_after = 0
    dirs = sorted({p.parent for p in root.rglob("*.parquet") if not p.name.startswith(".tmp-")})
    for d in dirs:
        parts = sorted(p for p in d.glob("*.parquet") if not p.name.startswith(".tmp-"))
        size = sum(p.stat().st_size for p in parts)
        files_before += len(parts)
        bytes_before += size
        if len(parts) < min_files:
            files_after += len(parts)
            bytes_after += size
            continue
        frame = pl.concat([pl.read_parquet(p) for p in parts], how="vertical")
        target = d / f"compact-{len(list(d.glob('compact-*.parquet')))}.parquet"
        write_parquet(frame, target)
        if pl.read_parquet(target).height != frame.height:
            raise RuntimeError(f"{target}: compacted file does not hold every row")
        for p in parts:
            if p != target:
                p.unlink()
        files_after += 1
        bytes_after += target.stat().st_size
    return files_before, files_after, bytes_before, bytes_after
