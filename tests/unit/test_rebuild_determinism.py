"""Invariant 10: staging is a function of raw and code. The same raw bytes, loaded into two separate data homes by
the real `load` path, give byte-identical staging files (a full `fin rebuild --from-raw` was last proven byte
identical on 2026-11-07, docs/evaluation/2026-11-07-stage-a-first-daily-run.md)."""

from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path
from typing import Any

import pytest

from fin.config import Zones
from fin.ingest.base import Connector, load
from fin.ingest.registry import connector
from fin.store.runs import IngestRun

FIX = Path(__file__).parents[1] / "fixtures"


def _fre_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n in ("fre_cia_aberta_2022.csv", "fre_cia_aberta_capital_social_2022.csv"):
            z.writestr(n, (FIX / "cvm_fre" / n).read_bytes())
    return buf.getvalue()


CASES: list[tuple[str, str, Any]] = [
    ("b3_fundosnet", "informe_rendimentos", lambda: (FIX / "b3_fundosnet" / "doc_1371379.xml").read_bytes()),
    ("cvm_fre", "fre_cia_aberta", _fre_zip),
]


def _staging_digest(z: Zones) -> dict[str, str]:
    return {
        str(p.relative_to(z.staging)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(z.staging.rglob("*.parquet"))
    }


@pytest.mark.parametrize(("source", "dataset", "blob"), CASES)
def test_same_raw_gives_byte_identical_staging(tmp_path: Path, source: str, dataset: str, blob: Any) -> None:
    data = blob()
    sha = hashlib.sha256(data).hexdigest()
    row = {"raw_sha256": sha, "ingest_run_id": "r", "dataset_id": dataset, "notes": "id=1371379",
           "request": "{\"params\": {\"id\": 1371379}}", "fetched_at": None, "source_reference_date": None}  # fmt: skip
    digests = []
    for home in ("a", "b"):
        z = Zones(tmp_path / home)
        c: Connector = connector(source)
        with IngestRun(z, "test") as run:
            load(c, z, run, data, dict(row))
        digests.append(_staging_digest(z))
    assert digests[0] and digests[0] == digests[1]
