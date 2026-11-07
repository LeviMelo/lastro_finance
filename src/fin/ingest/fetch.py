"""Fetch one request into the raw archive and the manifest (the `fetch(spec)` step of PLAN §4.12).

A request is identified by its canonical JSON (method, URL, params, body; credentials redacted). When the previous
fetch of the same request left an ETag or Last-Modified, the request is made conditional; a 304 records a manifest
row pointing at the object already held. Any other non-2xx is an error of the run, never an empty object.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from fin.ingest.http import FetchError, PoliteClient
from fin.store.manifest import ManifestRow, canonical_request
from fin.store.raw import RawStore
from fin.store.runs import IngestRun, utc_now


@dataclass(frozen=True)
class FetchSpec:
    source_id: str
    dataset_id: str
    url: str
    ext: str
    method: str = "GET"
    params: dict[str, Any] | None = None
    data: dict[str, Any] | None = None
    json: Any = None
    headers: dict[str, str] | None = None
    reference_date: date | None = None
    conditional: bool = True
    accept_status: frozenset[int] = field(default_factory=lambda: frozenset({200}))
    absent_status: frozenset[int] = frozenset()  # statuses meaning "not served (any more / yet)": logged, no error
    min_bytes: int = 0  # a 200 shorter than this is the source's "no data for that date" stub: absent, not stored
    locator: str | None = None  # e.g. "page=3"; the part of a multi-request payload this object is
    notes: str | None = None

    def request(self) -> dict[str, Any]:
        return {"method": self.method, "url": self.url, "params": self.params, "data": self.data, "json": self.json}


@dataclass(frozen=True)
class FetchOutcome:
    spec: FetchSpec
    row: ManifestRow
    new_object: bool  # the bytes were not in the archive before this fetch


class Fetcher:
    def __init__(self, run: IngestRun, raw: RawStore, client: PoliteClient, connector_version: str) -> None:
        self.run = run
        self.raw = raw
        self.client = client
        self.connector_version = connector_version

    def fetch(self, spec: FetchSpec) -> FetchOutcome | None:
        """The outcome, or None when the source answered with one of `spec.absent_status`."""
        request = canonical_request(spec.request())
        key = hashlib.sha256(request.encode("utf-8")).hexdigest()
        headers = dict(spec.headers or {})
        previous = self.run.manifest.latest_for_request(key) if spec.conditional else None
        if previous is not None:
            if previous["etag"]:
                headers["If-None-Match"] = previous["etag"]
            if previous["last_modified"]:
                headers["If-Modified-Since"] = previous["last_modified"]

        fetched_at = utc_now()
        resp = self.client.request(
            spec.method, spec.url, params=spec.params, data=spec.data, json=spec.json, headers=headers
        )
        if resp.status_code in spec.absent_status or (resp.status_code == 200 and len(resp.content) < spec.min_bytes):
            self.run.log(
                "fetch.absent",
                url=spec.url,
                status=resp.status_code,
                bytes=len(resp.content),
                reference_date=spec.reference_date,
            )
            return None

        if resp.status_code == 304 and previous is not None:
            row = ManifestRow(
                raw_sha256=previous["raw_sha256"],
                raw_ext=previous["raw_ext"],
                source_id=spec.source_id,
                dataset_id=spec.dataset_id,
                request=request,
                request_key=key,
                fetched_at=fetched_at,
                http_status=304,
                content_type=previous["content_type"],
                bytes=previous["bytes"],
                etag=resp.headers.get("ETag") or previous["etag"],
                last_modified=resp.headers.get("Last-Modified") or previous["last_modified"],
                source_reference_date=spec.reference_date,
                ingest_run_id=self.run.run_id,
                connector_version=self.connector_version,
                notes=spec.notes or spec.locator,
            )
            self.run.manifest.append(row)
            self.run.log("fetch.not_modified", url=spec.url, sha256=row.raw_sha256)
            return FetchOutcome(spec, row, new_object=False)

        if resp.status_code not in spec.accept_status:
            raise FetchError(spec.url, f"HTTP {resp.status_code}", status=resp.status_code)

        ref = self.raw.put_bytes(resp.content, spec.ext)
        row = ManifestRow(
            raw_sha256=ref.sha256,
            raw_ext=ref.ext,
            source_id=spec.source_id,
            dataset_id=spec.dataset_id,
            request=request,
            request_key=key,
            fetched_at=fetched_at,
            http_status=resp.status_code,
            content_type=resp.headers.get("Content-Type"),
            bytes=ref.size,
            etag=resp.headers.get("ETag"),
            last_modified=resp.headers.get("Last-Modified"),
            source_reference_date=spec.reference_date,
            ingest_run_id=self.run.run_id,
            connector_version=self.connector_version,
            notes=spec.notes or spec.locator,
        )
        self.run.manifest.append(row)
        self.run.log("fetch.stored", url=spec.url, sha256=ref.sha256, bytes=ref.size, new=ref.created)
        return FetchOutcome(spec, row, new_object=ref.created)
