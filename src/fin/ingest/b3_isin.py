"""B3's ISIN database (docs/sources/b3_isin.md): every Brazilian issuer code and ISIN B3 has assigned, with the issuer's
CNPJ: the official map from the 4-letter code of an ISIN (BR**PETR**ACNPR6) to a company.

`https://sistemaswebb3-listados.b3.com.br/isinProxy/IsinCall/GetTextDownload/` lists the files (measured 2026-11-08):
`geralPt` (full database, regenerated daily; 8.3 MB zip: EMISSOR.TXT 7.4 MB, NUMERACA.TXT 106 MB, Leiame.pdf),
`mensalPt`, and `diariosPt` (the last ~19 business days: EMISSOR.TXT plus NUMERACA_D.TXT, the day's new and changed
ISINs). `GetFileDownload/<base64(id)>` returns a zip. Cancelled issuer codes and ISINs are removed from the database
(KROT, CTIP, TBLE absent), so the daily change files are the only record of a cancellation: archived every day.

EMISSOR.TXT: `"code","name","cnpj","date"`, UTF-8, quoted, one issuer per line (69,803 on 2026-11-06); the date is
20180628 for every issuer migrated to the current system. Parsed to staging `emitter`. NUMERACA is archived, not
parsed yet.
"""

from __future__ import annotations

import base64
import csv
import io
import json
from collections.abc import Iterable
from datetime import date
from typing import Any, ClassVar

import polars as pl

from fin.config import Zones
from fin.ingest.base import Connector, Mode, Parsed
from fin.ingest.fetch import FetchSpec
from fin.ingest.http import BROWSER_UA
from fin.schema import Column, Contract, Rule

BASE = "https://sistemaswebb3-listados.b3.com.br/isinProxy/IsinCall"
FULL_EVERY_DAYS = 7

EMITTER = Contract(
    table="staging.b3_isin.emitter",
    version=1,
    description="An issuer code of B3's ISIN database with the issuer's name and CNPJ, as one file listed it.",
    columns=(
        Column(
            "code", pl.String, "4-character issuer code (letters 3-6 of its ISINs)", "código do emissor", nullable=False
        ),
        Column("name", pl.String, "issuer name as written", "nome do emissor"),
        Column("cnpj", pl.String, "issuer CNPJ, 14 digits as written", "CNPJ"),
        Column("since", pl.Date, "date field of the record (20180628 for migrated issuers)", "data", "date"),
    ),
    rules=(Rule("code_4", pl.col("code").str.len_chars() == 4),),
    key=("code", "raw_sha256"),
)
CONTRACTS = {"emitter": EMITTER}


def parse_emitter(data: bytes, name: str, row: dict[str, Any]) -> pl.DataFrame:
    text = data.decode("utf-8")
    out = []
    for i, f in enumerate(csv.reader(io.StringIO(text)), start=1):
        if len(f) != 4:
            raise ValueError(f"B3 ISIN {name} line {i}: {len(f)} fields")
        d = f[3].strip()
        out.append({
            "code": f[0], "name": f[1] or None, "cnpj": f[2] or None,
            "since": date(int(d[:4]), int(d[4:6]), int(d[6:])) if len(d) == 8 else None,
            "raw_locator": f"member={name};line={i}",
        })  # fmt: skip
    schema = {c.name: c.dtype for c in EMITTER.columns} | {"raw_locator": pl.String}
    return pl.DataFrame(out, schema=schema, orient="row").with_columns(
        pl.lit(row["raw_sha256"]).alias("raw_sha256"), pl.lit(row["ingest_run_id"]).alias("ingest_run_id")
    )


def parse_payload(blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
    notes = str(row.get("notes") or "")
    member = notes.split("|", 1)[1] if "|" in notes else ""
    if member.upper() == "EMISSOR.TXT":
        yield Parsed("emitter", "all", parse_emitter(blob, member, row))


class B3Isin(Connector):
    """The full ISIN database weekly and every daily change file (served ~19 business days back)."""

    source_id: ClassVar[str] = "b3_isin"
    version: ClassVar[str] = "1"
    user_agent: ClassVar[str | None] = BROWSER_UA
    contracts: ClassVar[dict[str, Any]] = CONTRACTS
    dedup_staging: ClassVar[bool] = True

    def __init__(self) -> None:
        self._held: set[str] = set()
        self._full_due = True

    def discover(self, mode: Mode, zones: Zones, **options: Any) -> Iterable[FetchSpec]:
        from fin.ingest.snapshots import held_rows, today_brt

        held = held_rows(zones, self.source_id, "daily")  # by generation date: the locator is constant (deltas)
        self._held = (
            {d.isoformat() for d in held["source_reference_date"].drop_nulls().to_list()} if held.height else set()
        )
        full = held_rows(zones, self.source_id, "full")
        last = max((t.date() for t in full["fetched_at"].to_list()), default=None) if full.height else None
        self._full_due = last is None or (today_brt() - last).days >= FULL_EVERY_DAYS
        yield FetchSpec(self.source_id, "files", f"{BASE}/GetTextDownload/", "json", reference_date=today_brt(),
                        conditional=False, min_bytes=20, locator="list")  # fmt: skip

    def _file(self, dataset: str, item: dict[str, Any]) -> FetchSpec:
        made = date.fromisoformat(str(item["dataGeracao"])[:10])
        enc = base64.b64encode(str(item["id"]).encode()).decode()
        # a constant locator: each member is stored as a delta of the same member of the previous file (ADR-0014)
        return FetchSpec(self.source_id, dataset, f"{BASE}/GetFileDownload/{enc}", "zip", reference_date=made,
                         conditional=False, min_bytes=1000, locator=dataset, unpack_members=True)  # fmt: skip

    def follow(self, spec: FetchSpec, blob: bytes) -> Iterable[FetchSpec]:
        if spec.dataset_id != "files":
            return []
        doc = json.loads(blob)
        out = [
            self._file("daily", d) for d in doc.get("diariosPt") or [] if str(d["dataGeracao"])[:10] not in self._held
        ]
        if self._full_due and doc.get("geralPt"):
            out.append(self._file("full", doc["geralPt"]))
        return out

    def parse(self, blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
        return parse_payload(blob, row)
