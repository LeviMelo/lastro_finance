"""B3 `PR<YYMMDD>.zip` of pesquisapregao (BVBG.086.01 Price Report) -> staging `price_report`.

See docs/sources/b3_settlement_prices.md.

The archived object is a zip holding one zip (`PR<YYMMDD>.zip`) of several `BVBG.086.01_<id>.xml` files (3-4 in
2018-2026, 21-132 MB each). Each XML is a snapshot of the whole day taken at a different time (`BizGrpDtls/CreDtAndTm`
in its header; the UTC time of the same instant is the `CreDt` of every message), so the files overlap: 95-99% of the
`PricRpt` elements are byte-identical across them. A `PricRpt` is one instrument on one day (trades, best bid/ask,
open interest and, for futures, the settlement); a forward (`...T` ticker, `DaysToSttlm`) has one per term.

Merge rule (from the recon of 2026-11-07): one row per (`trade_date`, `ticker`, `days_to_settlement`). The latest
snapshot's element wins, except that an element that carries the settlement `AdjstdQt` is never replaced by one that
lacks it (in 2018-01-02 the first snapshot has no `AdjstdQt` for INDG18, the next ones do). The rows say what was
merged: `snapshots_seen` (files holding the key) and `snapshots_differ` (their elements are not byte-identical once
whitespace is removed), so a disagreement is visible instead of picked silently (PLAN 4.1 invariant 7).

The files are read as bytes, never as a DOM (130 MB each): a message is cut with `find`, whitespace between tags is
removed, and leaves are read with one regex. Every leaf must be a known one, every number must cast to its declared
scale, `Prtry` must be `8` and `MktIdrCd` `BVMF`, the price fields of a message must share one currency (EqvtVal is
always BRL and kept apart), and the messages of a file must be as many as its header declares (`TtlNbOfMsg`):
anything else raises `LayoutError` and nothing is staged. Dates inside the file are those of the XML (`TradDt`): a few
messages are dated the next business day and are kept as they are.
"""

from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import polars as pl
import zstandard

from fin.ingest.base import NotData, Parsed
from fin.schema import Column, Contract, Rule


class LayoutError(ValueError):
    pass


P4, V2, W12 = pl.Decimal(38, 4), pl.Decimal(38, 2), pl.Decimal(38, 12)
KINDS: dict[str, Any] = {"str": pl.String, "int": pl.Int64, "p4": P4, "v2": V2, "w12": W12}
PRICE_TAGS = frozenset(
    {
        "BestBidPric", "BestAskPric", "FrstPric", "MinPric", "MaxPric", "TradAvrgPric", "LastPric", "AdjstdQt",
        "PrvsAdjstdQt", "VartnPts", "AdjstdValCtrct", "MaxTradLmt", "MinTradLmt",
    }
)  # fmt: skip
# the `Ccy` attribute of these is the quote currency of the message (checked to be one)

# XML leaf, column, kind, description, unit
_CCY = "quote currency of the message (price_ccy)"
FIELDS: tuple[tuple[str, str, str, str, str], ...] = (
    ("TradQty", "trade_count", "int", "number of trades (TradDtls/TradQty)", "trades"),
    (
        "DaysToSttlm",
        "days_to_settlement",
        "int",
        "days to settlement (TradDtls/DaysToSttlm; forwards)",
        "calendar days",
    ),
    ("MktDataStrmId", "market_data_stream", "str", "market data stream: E, T or O (meaning not documented)", ""),
    ("NtlFinVol", "volume_brl", "v2", "financial volume, national (BRL)", "BRL"),
    ("IntlFinVol", "volume_usd", "v2", "financial volume, international (USD)", "USD"),
    ("OpnIntrst", "open_interest", "int", "open interest, contracts", "contracts"),
    ("FinInstrmQty", "quantity", "int", "instruments traded (contracts, shares)", "units"),
    ("BestBidPric", "best_bid", "p4", "best bid at the close", _CCY),
    ("BestAskPric", "best_ask", "p4", "best ask at the close", _CCY),
    ("FrstPric", "first_price", "p4", "first trade price; a RATE for DI1 (% a.a.)", _CCY),
    ("MinPric", "min_price", "p4", "lowest trade price (a rate for DI1)", _CCY),
    ("MaxPric", "max_price", "p4", "highest trade price (a rate for DI1)", _CCY),
    ("TradAvrgPric", "avg_price", "p4", "average trade price (a rate for DI1)", _CCY),
    ("LastPric", "last_price", "p4", "last trade price (a rate for DI1)", _CCY),
    ("RglrTxsQty", "regular_trade_count", "int", "regular trades", "trades"),
    ("RglrTraddCtrcts", "regular_quantity", "int", "instruments traded in regular trades", "units"),
    ("NtlRglrVol", "regular_volume_brl", "v2", "regular-trade financial volume, national (BRL)", "BRL"),
    ("IntlRglrVol", "regular_volume_usd", "v2", "regular-trade financial volume, international (USD)", "USD"),
    ("NonRglrTxsQty", "nonregular_trade_count", "int", "non-regular trades", "trades"),
    ("NonRglrTraddCtrcts", "nonregular_quantity", "int", "instruments traded in non-regular trades", "units"),
    ("NtlNonRglrVol", "nonregular_volume_brl", "v2", "non-regular financial volume, national (BRL)", "BRL"),
    ("IntlNonRglrVol", "nonregular_volume_usd", "v2", "non-regular financial volume, international (USD)", "USD"),
    ("OscnPctg", "oscillation_pct", "p4", "price oscillation of the day, % as written (1.77 = 1.77%)", "%"),
    ("AdjstdQt", "settlement_price", "p4", "settlement price (ajuste); the PU for DI1", _CCY),
    ("AdjstdQtTax", "settlement_rate", "p4", "settlement rate, % a.a. (DI1, DDI, FRC...)", "% a.a."),
    ("AdjstdQtStin", "settlement_status", "str", "F or U, meaning not documented (F on the usual settlement)", ""),
    ("PrvsAdjstdQt", "prev_settlement_price", "p4", "previous day's settlement price", _CCY),
    ("PrvsAdjstdQtTax", "prev_settlement_rate", "p4", "previous day's settlement rate, % a.a.", "% a.a."),
    ("PrvsAdjstdQtStin", "prev_settlement_status", "str", "F or U for the previous settlement", ""),
    ("VartnPts", "settlement_change", "p4", "settlement change in points (VartnPts)", _CCY),
    ("AdjstdValCtrct", "settlement_value_per_contract", "w12", "daily adjustment per contract", _CCY),
    ("MaxTradLmt", "max_trade_limit", "p4", "maximum price limit of the day", _CCY),
    ("MinTradLmt", "min_trade_limit", "p4", "minimum price limit of the day", _CCY),
    ("EqvtVal", "equivalent_value_brl", "p4", "equivalent value (EqvtVal), always BRL in the files", "BRL"),
)
_BY_TAG = {f[0]: f for f in FIELDS}
_FIXED = {"Dt", "TckrSymb", "Id", "Prtry", "MktIdrCd"}  # key, instrument id and two constants
KEYS = ("trade_date", "ticker")

PRICE_REPORT = Contract(
    table="staging.b3_pesquisapregao.price_report",
    version=1,
    description="One instrument on one day of a B3 BVBG.086.01 price report (snapshots merged, see the module).",
    columns=(
        Column("file_date", pl.Date, "date of the PR file requested (its name)", "data do arquivo", "date", False),
        Column("trade_date", pl.Date, "TradDt/Dt of the message", "data do pregão", "date", False),
        Column("ticker", pl.String, "SctyId/TckrSymb as published", "ticker", "", False),
        Column(
            "b3_instrument_id",
            pl.Int64,
            "FinInstrmId/OthrId/Id (scheme 8, B3 numeric instrument id)",
            "id do instrumento",
            "B3 id",
        ),
        *(Column(name, KINDS[kind], en, tag.lower(), unit) for tag, name, kind, en, unit in FIELDS if tag != "EqvtVal"),
        Column("equivalent_value_brl", P4, "equivalent value (EqvtVal), always BRL in the files", "EqvtVal", "BRL"),
        Column("price_ccy", pl.String, "Ccy attribute shared by the price fields of the message", "moeda", "ISO 4217"),
        Column(
            "snapshot_at",
            pl.Datetime("us", "UTC"),
            "UTC time of the chosen snapshot (AppHdr/CreDt of its first message)",
            "momento do snapshot",
            "UTC",
        ),
        Column("snapshots_seen", pl.Int16, "snapshot files of the day holding this ticker", "", "files", False),
        Column(
            "snapshots_differ",
            pl.Boolean,
            "the ticker's elements differ between the snapshots (whitespace removed)",
            "",
            "",
            False,
        ),
    ),
    rules=(
        Rule("open_interest_not_negative", (pl.col("open_interest") >= 0) | pl.col("open_interest").is_null()),
        Rule("quantity_not_negative", (pl.col("quantity") >= 0) | pl.col("quantity").is_null()),
        Rule("volume_not_negative", (pl.col("volume_brl") >= 0) | pl.col("volume_brl").is_null()),
        Rule("snapshots_seen_positive", pl.col("snapshots_seen") >= 1),
    ),
    key=("trade_date", "ticker", "days_to_settlement", "raw_sha256"),
)
CONTRACTS = {"price_report": PRICE_REPORT}

_START = re.compile(rb"<TradDt><Dt>(\d{4}-\d{2}-\d{2})</Dt></TradDt><SctyId><TckrSymb>([^<]+)</TckrSymb></SctyId>")
_LEAF = re.compile(rb"<(\w+)(?: Ccy=\"(\w+)\")?>([^<]*)</\1>")
_GAP = re.compile(rb">\s+<")
_TERM = re.compile(rb"<DaysToSttlm>(\d+)</DaysToSttlm>")
_HEAD_TOTAL = re.compile(rb"<TtlNbOfMsg>(\d+)</TtlNbOfMsg>")
_HEAD_AT = re.compile(rb"<CreDtAndTm>([^<]+)</CreDtAndTm>")
_APP_AT = re.compile(rb"<CreDt>(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})Z</CreDt>")
_OPEN, _CLOSE = b"<PricRpt>", b"</PricRpt>"


ZSTD_MAGIC = bytes.fromhex("28b52ffd")
# Stored form of a downloaded PR (ADR-0031): the day's XML snapshots, byte for byte, in a deterministic tar, compressed
# with zstd level 16 and long-distance matching over a 256 MB window, so a snapshot is coded against the previous one
# (95-99 % identical). 2026-11-06: 11.08 MB as served, 7.28 MB as 4 XML at zstd 19, 2.98 MB so (36 s).
PR_LEVEL, PR_WINDOW_LOG = 16, 28


def extract_snapshots(blob: bytes) -> tuple[bytes, str, dict[str, Any]]:
    """What is kept of a PR download: its XML snapshots in a `.tzst`, and a record of the zip's structure."""
    import tarfile

    try:
        outer = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile as e:
        raise NotData(f"B3 PR: not a zip ({e})") from e
    record: dict[str, Any] = {"outer": [{"name": i.filename, "size": i.file_size, "crc32": i.CRC}
                                        for i in outer.infolist()], "inner": []}  # fmt: skip
    members = snapshots(blob)
    for i in outer.infolist():
        data = outer.read(i)
        if data[:2] == b"PK":
            inner = zipfile.ZipFile(io.BytesIO(data))
            record["inner"] += [{"name": j.filename, "size": j.file_size, "crc32": j.CRC, "date_time": j.date_time}
                                for j in inner.infolist()]  # fmt: skip
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        for name, data in sorted(members):
            info = tarfile.TarInfo(name)  # fixed metadata: equal snapshots give equal bytes (content addressing)
            info.size, info.mtime, info.mode = len(data), 0, 0o644
            tar.addfile(info, io.BytesIO(data))
    params = zstandard.ZstdCompressionParameters.from_level(
        PR_LEVEL, enable_ldm=True, window_log=PR_WINDOW_LOG, write_content_size=True
    )
    kept = zstandard.ZstdCompressor(compression_params=params).compress(buf.getvalue())
    record["kept"] = {"format": "tar+zstd", "level": PR_LEVEL, "window_log": PR_WINDOW_LOG, "members": len(members)}
    return kept, "tzst", record


def _tzst_members(blob: bytes) -> list[tuple[str, bytes]]:
    import tarfile

    reader = zstandard.ZstdDecompressor(max_window_size=2**31).stream_reader(io.BytesIO(blob))
    out: list[tuple[str, bytes]] = []
    with tarfile.open(fileobj=reader, mode="r|") as tar:
        for info in tar:
            f = tar.extractfile(info)
            if f is None:
                raise LayoutError(f"B3 PR: tar member {info.name} is not a file")
            out.append((info.name, f.read()))
    return out


def snapshots(blob: bytes) -> list[tuple[str, bytes]]:
    """(member name, XML bytes) of the archived PR object: zip -> zip -> XML files as served, or the `.tzst` kept
    since ADR-0031 (`extract_snapshots`). Nothing is executed."""
    if blob[:4] == ZSTD_MAGIC:
        members = _tzst_members(blob)
        if not members:
            raise NotData("B3 PR: empty archive")
        return members

    def walk(data: bytes, depth: int) -> list[tuple[str, bytes]]:
        # zip -> zip -> XML as a rule; 2023-07-19 nests one level more (zip -> zip -> zips -> XML)
        if depth > 4:
            raise LayoutError("B3 PR: zips nested more than 4 deep")
        z = zipfile.ZipFile(io.BytesIO(data))
        found: list[tuple[str, bytes]] = []
        for name in z.namelist():
            inner = z.read(name)
            found += walk(inner, depth + 1) if inner[:2] == b"PK" else [(name, inner)]
        return found

    try:
        members = walk(blob, 0)
    except zipfile.BadZipFile as e:
        raise NotData(f"B3 PR: not a zip ({e})") from e
    if not members:
        raise NotData("B3 PR: empty zip")
    bad = [n for n, _ in members if not n.endswith(".xml")]
    if bad:
        raise LayoutError(f"B3 PR: unexpected members {bad}")
    return members


def _header(xml: bytes, name: str) -> tuple[int, str, datetime | None]:
    head = xml[: xml.find(_OPEN) if _OPEN in xml else len(xml)]
    total, at, app = _HEAD_TOTAL.search(head), _HEAD_AT.search(head), _APP_AT.search(head)
    if not total or not at:
        raise LayoutError(f"B3 PR {name}: no TtlNbOfMsg / CreDtAndTm in the header")
    utc = datetime.fromisoformat(app.group(1).decode()).replace(tzinfo=UTC) if app else None
    return int(total.group(1)), at.group(1).decode(), utc


def _messages(xml: bytes, name: str) -> Iterable[tuple[int, bytes]]:
    pos, n = 0, 0
    while (i := xml.find(_OPEN, pos)) >= 0:
        j = xml.find(_CLOSE, i)
        if j < 0:
            raise LayoutError(f"B3 PR {name}: unterminated PricRpt after message {n}")
        n += 1
        yield n, _GAP.sub(b"><", xml[i + len(_OPEN) : j].strip())
        pos = j + len(_CLOSE)


def _has_settlement(body: bytes) -> bool:
    return b"<AdjstdQt " in body or b"<AdjstdQt>" in body


@dataclass
class Pick:
    """The chosen message of one (trade date, ticker) and what the other snapshots said about it."""

    member: str
    number: int
    body: bytes
    utc: datetime | None
    seen: int = 1
    differ: bool = False


def merge(members: list[tuple[str, bytes]]) -> dict[tuple[str, str, str], Pick]:
    """One chosen message per (trade date, ticker, term), by the rule of the module docstring."""
    order: list[tuple[str, str, bytes, int, datetime | None]] = []
    for name, xml in members:
        total, at, utc = _header(xml, name)
        order.append((at, name, xml, total, utc))
    order.sort(key=lambda t: (t[0], t[1]))
    chosen: dict[tuple[str, str, str], Pick] = {}
    for _at, name, xml, total, utc in order:
        count = 0
        for n, body in _messages(xml, name):
            count += 1
            m = _START.match(body)
            if not m:
                raise LayoutError(f"B3 PR {name}: message {n} does not start with TradDt and TckrSymb")
            term = _TERM.search(body)
            key = (m.group(1).decode(), m.group(2).decode(), term.group(1).decode() if term else "")
            cur = chosen.get(key)
            if cur is None:
                chosen[key] = Pick(name, n, body, utc)
                continue
            cur.seen += 1
            cur.differ = cur.differ or cur.body != body
            if _has_settlement(body) or not _has_settlement(cur.body):
                cur.member, cur.number, cur.body, cur.utc = name, n, body, utc
        if count != total:
            raise LayoutError(f"B3 PR {name}: header declares {total} messages, found {count}")
    return chosen


def _leaves(body: bytes, member: str, n: int) -> dict[str, str | None]:
    row: dict[str, str | None] = {}
    seen: set[str] = set()
    ccy: set[str] = set()
    for m in _LEAF.finditer(body):
        tag, c, val = m.group(1).decode(), m.group(2), m.group(3).decode()
        if tag in seen:
            raise LayoutError(f"B3 PR {member} message {n}: {tag} repeated")
        seen.add(tag)
        if tag in _BY_TAG:
            row[tag] = val
            if tag in PRICE_TAGS and c is not None:
                ccy.add(c.decode())
            if tag == "EqvtVal" and c != b"BRL":
                raise LayoutError(f"B3 PR {member} message {n}: EqvtVal currency {c!r}, expected BRL")
        elif tag not in _FIXED:
            raise LayoutError(f"B3 PR {member} message {n}: unknown element {tag}")
    if len(ccy) > 1:
        raise LayoutError(f"B3 PR {member} message {n}: price fields in several currencies {sorted(ccy)}")
    pr = re.findall(rb"<Prtry>([^<]*)</Prtry>", body)
    mk = re.findall(rb"<MktIdrCd>([^<]*)</MktIdrCd>", body)
    if pr != [b"8"] or mk != [b"BVMF"]:
        raise LayoutError(f"B3 PR {member} message {n}: identifier scheme {pr} / market {mk}, expected 8 / BVMF")
    row["price_ccy"] = next(iter(ccy)) if ccy else None
    ident = re.search(rb"<OthrId><Id>([^<]*)</Id>", body)
    row["b3_instrument_id"] = ident.group(1).decode() if ident else None
    return row


def _file_date(blob_name: str, row: dict[str, Any]) -> date | None:
    ref = row.get("source_reference_date")
    if isinstance(ref, date):
        return ref
    m = re.search(r"PR(\d{2})(\d{2})(\d{2})", blob_name + str(row.get("notes") or ""))
    return date(2000 + int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def _typed(text: pl.DataFrame) -> pl.DataFrame:
    """The text frame cast to the contract's types; a value that is lost or would be rounded is a layout change."""
    exprs: list[pl.Expr] = [
        pl.col("trade_date").str.to_date("%Y-%m-%d"),
        pl.col("ticker"),
        pl.col("b3_instrument_id").cast(pl.Int64, strict=False),
        pl.col("price_ccy"),
    ]
    for _tag, name, kind, *_ in FIELDS:
        exprs.append(pl.col(name) if kind == "str" else pl.col(name).str.strip_chars().cast(KINDS[kind], strict=False))
    typed = text.select(*exprs)
    for _tag, name, kind, *_ in FIELDS:
        if kind == "str":
            continue
        src = text[name].str.strip_chars()
        lost = src.is_not_null() & typed[name].is_null()
        if lost.any():
            bad = src.filter(lost).head(2).to_list()
            raise LayoutError(f"B3 PR: {int(lost.sum())} values of {name} do not cast to {kind}, e.g. {bad}")
        dtype = KINDS[kind]
        if isinstance(dtype, pl.Decimal):
            more = src.str.contains(rf"^-?\d*\.\d{{{(dtype.scale or 0) + 1},}}$")
            if more.any():
                raise LayoutError(
                    f"B3 PR: {name} has more than {dtype.scale} decimals, e.g. {src.filter(more).head(2).to_list()}"
                )
    return typed


def parse_price_report(blob: bytes, row: dict[str, Any]) -> pl.DataFrame:
    chosen = merge(snapshots(blob))
    cols: dict[str, list[Any]] = {n: [] for n in ["trade_date", "ticker", "b3_instrument_id", "price_ccy"]}
    cols |= {f[1]: [] for f in FIELDS}
    snap_at, seen, differ, locator = [], [], [], []
    for (day, ticker, _term), p in sorted(chosen.items()):
        leaf = _leaves(p.body, p.member, p.number)
        cols["trade_date"].append(day)
        cols["ticker"].append(ticker)
        cols["b3_instrument_id"].append(leaf["b3_instrument_id"])
        cols["price_ccy"].append(leaf["price_ccy"])
        for tag, name, *_ in FIELDS:
            cols[name].append(leaf.get(tag))
        snap_at.append(p.utc)
        seen.append(p.seen)
        differ.append(p.differ)
        locator.append(f"member={p.member};message={p.number}")
    typed = _typed(pl.DataFrame(cols, schema={k: pl.String for k in cols}))
    file_date = _file_date(str(row.get("notes") or ""), row)
    return typed.with_columns(
        pl.lit(file_date, dtype=pl.Date).alias("file_date"),
        pl.Series("snapshot_at", snap_at, dtype=pl.Datetime("us", "UTC")),
        pl.Series("snapshots_seen", seen, dtype=pl.Int16),
        pl.Series("snapshots_differ", differ, dtype=pl.Boolean),
        pl.Series("raw_locator", locator, dtype=pl.String),
        pl.lit(row["raw_sha256"]).alias("raw_sha256"),
        pl.lit(row["ingest_run_id"]).alias("ingest_run_id"),
    ).select(PRICE_REPORT.names)


def parse_payload(blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
    if str(row["dataset_id"]) != "PR":  # the TS (TaxaSwap) files of the same connector are b3_taxaswap's
        return
    df = parse_price_report(blob, row)
    fd = _file_date(str(row.get("notes") or ""), row)
    yield Parsed("price_report", f"file_date={fd}" if fd is not None else "unknown", df)
