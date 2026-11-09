"""The CVM IPE filings that prove a stock event, read for the ratio they state (docs/sources/cvm_ipe.md §docs).

A filing link comes from core `corporate_event.ipe_link` (`ipe_evidence`: a filing of the issuer whose subject names
the event, around its date). The ratio of many events comes from Yahoo or from B3's price move, both shown wrong at
times: TELB4 2011, Yahoo 1:10, the filing "10.000 (dez mil) ações para 1 (uma)"; BTTL3 2015, price 24.1x, the filing
"25 (vinte e cinco) ... para 1 (uma)". So each linked filing of an event whose ratio no B3 event list states is
fetched once (RAD `frmDownloadDocumento`, served as PDF, Word 97, docx or HTML whatever the Content-Type says), and
its text is searched for the ratio sentences of a regrouping, split or bonus. Parsed to staging `ipe_ratio`: every
candidate ratio of a filing, as new shares per old, with the sentence it came from. `core/events.py`
(`filing_ratios`) keeps the candidate that fits the price move.
"""

from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Iterable
from fractions import Fraction
from typing import Any, ClassVar

import polars as pl

from fin.config import Zones
from fin.ingest.base import Connector, Mode, NotData, Parsed
from fin.ingest.fetch import FetchSpec
from fin.ingest.http import BROWSER_UA
from fin.schema import Column, Contract, Rule

IPE_RATIO = Contract(
    table="staging.cvm_ipe_docs.ipe_ratio",
    version=1,
    description="A stock-event ratio stated in an IPE filing: new shares per old, with the sentence it was read from.",
    columns=(
        Column("ipe_link", pl.String, "RAD download link of the filing", "link", nullable=False),
        Column("kind", pl.String, "regrouping, split or bonus wording that matched", "tipo", nullable=False),
        Column("new_shares", pl.Int64, "shares after, per `old_shares`", "ações novas", "shares", nullable=False),
        Column("old_shares", pl.Int64, "shares before", "ações antigas", "shares", nullable=False),
        Column("snippet", pl.String, "the sentence, whitespace collapsed", "trecho"),
        Column("doc_format", pl.String, "pdf, doc, docx or html, from the bytes", "formato"),
    ),
    rules=(Rule("positive", (pl.col("new_shares") > 0) & (pl.col("old_shares") > 0)),),
    key=("ipe_link", "kind", "new_shares", "old_shares", "raw_sha256"),
)
CONTRACTS = {"ipe_ratio": IPE_RATIO}

N = r"(\d{1,3}(?:\.\d{3})+|\d+)"  # 10.000 or 25
SHARE = r"a[çc](?:[ãa]o|[õo]es)"
# written-out numbers in parentheses, "(vinte e cinco)", are dropped before matching
PATTERNS: tuple[tuple[str, re.Pattern[str], bool], ...] = (
    # "à razão de 25 ações para 1 ação", "na proporção de 10.000 ações para 1", "grupamento de 4 para 1"
    (
        "ratio",
        re.compile(
            rf"(?:raz[ãa]o|propor[çc][ãa]o|fator|grupamento|desdobramento)\s+de\s+{N}\s+(?:{SHARE}\s+)?"
            rf"(?:[^.;]{{0,120}}?)\b(?:para|em)\s+{N}\b"
        ),
        False,
    ),
    # "cada 1 ação ... será desdobrada em 4 ações", "cada 10 ações ... serão grupadas em 1"
    (
        "each",
        re.compile(
            rf"cada\s+{N}\s+(?:{SHARE}\s+)?(?:[^.;]{{0,160}}?)\b(?:desdobrad[ao]s?|grupad[ao]s?|"
            rf"representad[ao]s?|convertid[ao]s?)\s+(?:em|por)\s+{N}\b"
        ),
        False,
    ),
    # "1 nova ação para cada 10 ações" (bonus): new = old + given
    (
        "bonus",
        re.compile(rf"{N}\s+(?:\w+\s+){{0,2}}nova?s?\s+{SHARE}?\s*(?:[^.;]{{0,60}}?)\bpara\s+cada\s+{N}\b"),
        True,
    ),
)
BONUS_PCT = re.compile(r"bonifica[çc][ãa]o[^.;]{0,120}?\b(\d{1,3}(?:,\d+)?)\s*%")


def doc_text(blob: bytes) -> tuple[str, str]:
    """The filing's text and format, read from the bytes (RAD sends every format as text/html)."""
    if blob[:5] == b"%PDF-":
        import pypdfium2 as pdfium

        from fin.ingest.b3_bdi_pdf import PDFIUM

        with PDFIUM:
            doc = pdfium.PdfDocument(blob)
            try:
                return "\n".join(doc[i].get_textpage().get_text_range() for i in range(len(doc))), "pdf"
            finally:
                doc.close()
    if blob[:8] == bytes.fromhex("d0cf11e0a1b11ae1"):  # Word 97: text runs, cp1252 or UTF-16
        runs = [m.group(0) for enc in ("cp1252", "utf-16-le")
                for m in re.finditer(r"[^\x00-\x08\x0b-\x1f\x7f]{20,}", blob.decode(enc, errors="ignore"))]  # fmt: skip
        return "\n".join(runs), "doc"
    if blob[:2] == b"PK":
        try:
            z = zipfile.ZipFile(io.BytesIO(blob))
            xml = z.read("word/document.xml").decode("utf-8", errors="replace")
        except (zipfile.BadZipFile, KeyError) as e:
            raise NotData(f"IPE filing: zip without word/document.xml ({e})") from e
        return re.sub(r"<[^>]+>", " ", xml.replace("</w:p>", "\n")), "docx"
    text = blob.decode("utf-8", errors="strict") if _utf8(blob) else blob.decode("cp1252", errors="replace")
    return re.sub(r"<[^>]+>", " ", text), "html"


def _utf8(b: bytes) -> bool:
    try:
        b.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _int(s: str) -> int:
    return int(s.replace(".", ""))


def ratios(text: str) -> list[dict[str, Any]]:
    """Every ratio sentence of a filing: (kind, new shares, old shares, sentence). A "de A para B" sentence is a
    regrouping when A > B (A old become B new) and a split when A < B (A old become B new): both read A old, B new."""
    t = " ".join(re.sub(r"\([^()]{0,80}\)", " ", text.lower()).split())
    out: list[dict[str, Any]] = []
    for kind, pat, bonus in PATTERNS:
        for m in pat.finditer(t):
            a, b = _int(m.group(1)), _int(m.group(2))
            if not a or not b or (a == b and not bonus):
                continue
            new, old = (a + b, b) if bonus else (b, a)
            out.append({"kind": kind, "new_shares": new, "old_shares": old, "snippet": m.group(0)[:300]})
    for m in BONUS_PCT.finditer(t):
        pct = Fraction(m.group(1).replace(",", "."))
        if 0 < pct <= 1000:
            f = 1 + pct / 100
            out.append({"kind": "bonus_pct", "new_shares": f.numerator, "old_shares": f.denominator,
                        "snippet": m.group(0)[:300]})  # fmt: skip
    return out


def _link(notes: object) -> str:
    """The filing link of a manifest row (`ipe_link=<url>`, then `;record=<sha>` added by the fetcher)."""
    return str(notes or "").removeprefix("ipe_link=").split(";record=")[0]


def sniff(blob: bytes) -> tuple[bytes, str, dict[str, Any]]:
    """Stored as received, under the extension its bytes show (RAD's Content-Type is always text/html)."""
    if len(blob) < 16384 and (b"is unavailable" in blob or b"ENET Download de Documento" in blob):
        raise ValueError("RAD busy or empty download page")  # an error: not stored, asked again next run
    fmt = ("pdf" if blob[:5] == b"%PDF-" else "doc" if blob[:4] == bytes.fromhex("d0cf11e0")
           else "docx" if blob[:2] == b"PK" else "html")  # fmt: skip
    return blob, fmt, {"format": fmt, "bytes": len(blob)}


def parse_payload(blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
    text, fmt = doc_text(blob)
    found = ratios(text)
    link = _link(row.get("notes"))
    schema = {c.name: c.dtype for c in IPE_RATIO.columns}
    rows = [r | {"ipe_link": link, "doc_format": fmt} for r in found]
    df = pl.DataFrame(rows, schema=schema, orient="row") if rows else pl.DataFrame(schema=schema)
    df = df.with_columns(
        pl.lit("text").alias("raw_locator"),
        pl.lit(row["raw_sha256"]).alias("raw_sha256"),
        pl.lit(row["ingest_run_id"]).alias("ingest_run_id"),
    )
    yield Parsed("ipe_ratio", "all", df)


class CvmIpeDocs(Connector):
    """Fetches, once, each IPE filing linked to a stock event whose ratio no B3 event list states."""

    source_id: ClassVar[str] = "cvm_ipe_docs"
    version: ClassVar[str] = "1"
    user_agent: ClassVar[str | None] = BROWSER_UA
    contracts: ClassVar[dict[str, Contract]] = CONTRACTS
    concurrency: ClassVar[int] = 2  # RAD is shared with the restatement backfill
    cookies: ClassVar[bool] = False
    # RAD under load answers 200 with an empty 4.3 KB "ENET Download de Documento" page; a retry returns the filing
    # (docs/sources/cvm_ipe.md §4; 255 of 263 first answers on 2026-11-09, while the RAD backfill ran)
    busy_marker: ClassVar[bytes | None] = b"ENET Download de Documento"
    timeout: ClassVar[float] = 300.0

    def discover(self, mode: Mode, zones: Zones, **options: Any) -> Iterable[FetchSpec]:
        from fin.store.manifest import Manifest

        ev = zones.core / "corporate_event" / "corporate_event.parquet"
        if not ev.exists():
            return
        links = (
            pl.read_parquet(ev)
            .filter(pl.col("event_type").is_in(["SPLIT", "REVERSE_SPLIT", "BONUS"]) & pl.col("ipe_link").is_not_null()
                    & ~pl.col("sources").fill_null("").str.contains("b3_company_events"))
            .select("ipe_link").unique().sort("ipe_link")["ipe_link"].to_list()
        )  # fmt: skip
        held = (
            Manifest(zones.manifest)
            .read()
            .filter((pl.col("source_id") == self.source_id) & (pl.col("http_status") == 200))
        )
        # the empty shells stored by the first run (2026-11-09) are not filings: asked again
        held = held.filter(~((pl.col("raw_ext") == "html") & (pl.col("bytes") < 16384)))
        have = {_link(n) for n in held["notes"].drop_nulls().to_list()} if held.height else set()
        for link in links:
            if link in have:
                continue
            note = f"ipe_link={link}"
            proto = re.search(r"numProtocolo=(\d+)", link)
            yield FetchSpec(self.source_id, "document", link, "html", conditional=False, min_bytes=200,
                            locator=f"protocolo={proto.group(1) if proto else link}", extract=sniff,
                            notes=note)  # fmt: skip

    def parse(self, blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
        return parse_payload(blob, row)
