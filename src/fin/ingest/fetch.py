"""Fetch one request into the raw archive and the manifest (the `fetch(spec)` step of PLAN §4.12).

A request is identified by its canonical JSON (method, URL, params, body; credentials redacted). When the previous
fetch of the same request left an ETag or Last-Modified, the request is made conditional; a 304 records a manifest
row pointing at the object already held. Any other non-2xx is an error of the run, never an empty object.

**Unpacked zips (ADR-0014).** With `unpack_members`, a zip that a source re-ships whole (CVM's weekly yearly files) is
stored as its members, each a raw object of its own and a delta of the same member's previous version, plus a small
JSON record of the zip (its sha256, size and each member's name, CRC-32, size and sha256). The member bytes are the
source's data exactly (CRC-checked); the zip's compressed bytes are transport and are not kept.
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
    content: str | None = None  # a raw request body (e.g. a SOAP envelope), sent UTF-8 encoded
    headers: dict[str, str] | None = None
    reference_date: date | None = None
    conditional: bool = True
    accept_status: frozenset[int] = field(default_factory=lambda: frozenset({200}))
    absent_status: frozenset[int] = frozenset()  # statuses meaning "not served (any more / yet)": logged, no error
    min_bytes: int = 0  # a 200 shorter than this is the source's "no data for that date" stub: absent, not stored
    # a 200 whose Content-Type starts with none of these is an error page served as success: an error, not stored
    content_types: tuple[str, ...] = ()
    unpack_members: bool = False  # a zip stored as its members (ADR-0014)
    locator: str | None = None  # e.g. "page=3"; the part of a multi-request payload this object is
    notes: str | None = None

    def request(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "method": self.method,
            "url": self.url,
            "params": self.params,
            "data": self.data,
            "json": self.json,
        }
        if self.content is not None:  # only when set: the request key of every other request stays as it was
            out["content"] = self.content
        return out


@dataclass(frozen=True)
class FetchOutcome:
    spec: FetchSpec
    row: ManifestRow
    new_object: bool  # the bytes were not in the archive before this fetch
    members: tuple[tuple[ManifestRow, bool], ...] = ()  # unpacked zip members: (row, new object)


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
            spec.method,
            spec.url,
            params=spec.params,
            data=spec.data,
            json=spec.json,
            content=spec.content.encode("utf-8") if spec.content is not None else None,
            headers=headers,
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
        ctype = resp.headers.get("Content-Type") or ""
        if spec.content_types and not ctype.startswith(spec.content_types):
            raise FetchError(spec.url, f"HTTP {resp.status_code} with Content-Type {ctype!r}", status=resp.status_code)

        if spec.unpack_members:
            return self._unpack(spec, resp, request, key, fetched_at)
        base = self.run.manifest.previous_version(spec.source_id, spec.dataset_id, spec.notes or spec.locator)
        ref = self.raw.put_bytes(resp.content, spec.ext, base=base)
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

    def _unpack(self, spec: FetchSpec, resp: Any, request: str, key: str, fetched_at: Any) -> FetchOutcome:
        import io
        import json
        import zipfile

        blob: bytes = resp.content
        locator = spec.notes or spec.locator or ""
        listing: list[dict[str, Any]] = []
        members: list[tuple[ManifestRow, bool]] = []
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            for info in z.infolist():
                if info.is_dir():
                    continue
                data = z.read(info)  # raises on a CRC mismatch
                ext = info.filename.rsplit(".", 1)[-1].lower() if "." in info.filename else "bin"
                note = f"{locator}|{info.filename}"
                base = self.run.manifest.previous_version(spec.source_id, spec.dataset_id, note)
                ref = self.raw.put_bytes(data, ext, base=base)
                listing.append({"name": info.filename, "crc32": info.CRC, "size": info.file_size, "sha256": ref.sha256})
                mreq = json.dumps({"container": json.loads(request), "member": info.filename}, sort_keys=True)
                mrow = ManifestRow(
                    raw_sha256=ref.sha256,
                    raw_ext=ref.ext,
                    source_id=spec.source_id,
                    dataset_id=spec.dataset_id,
                    request=mreq,
                    request_key=hashlib.sha256(mreq.encode("utf-8")).hexdigest(),
                    fetched_at=fetched_at,
                    http_status=resp.status_code,
                    content_type="application/octet-stream; zip-member",
                    bytes=ref.size,
                    etag=None,
                    last_modified=None,
                    source_reference_date=spec.reference_date,
                    ingest_run_id=self.run.run_id,
                    connector_version=self.connector_version,
                    notes=note,
                )
                self.run.manifest.append(mrow)
                members.append((mrow, ref.created))
        record = json.dumps(
            {"zip_sha256": hashlib.sha256(blob).hexdigest(), "zip_size": len(blob), "members": listing},
            sort_keys=True,
            indent=1,
        ).encode("utf-8")
        ref = self.raw.put_bytes(record, "json")
        row = ManifestRow(
            raw_sha256=ref.sha256,
            raw_ext=ref.ext,
            source_id=spec.source_id,
            dataset_id=spec.dataset_id,
            request=request,
            request_key=key,
            fetched_at=fetched_at,
            http_status=resp.status_code,
            content_type="application/json; unpacked-zip",
            bytes=ref.size,
            etag=resp.headers.get("ETag"),
            last_modified=resp.headers.get("Last-Modified"),
            source_reference_date=spec.reference_date,
            ingest_run_id=self.run.run_id,
            connector_version=self.connector_version,
            notes=locator or None,
        )
        self.run.manifest.append(row)
        self.run.log("fetch.unpacked", url=spec.url, members=len(listing), zip_bytes=len(blob))
        return FetchOutcome(spec, row, new_object=ref.created, members=tuple(members))
