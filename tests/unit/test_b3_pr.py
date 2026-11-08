"""B3 PR (BVBG.086.01 price report): snapshot XML rebuilt from the real header and the committed real messages."""

from __future__ import annotations

import io
import re
import zipfile
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import polars as pl
import pytest

from fin.ingest import b3_pr
from fin.ingest.snapshots import B3PesquisaPregao

FIX = Path(__file__).parents[1] / "fixtures" / "b3_settlement_prices"
ROW: dict[str, Any] = {
    "raw_sha256": "a" * 64,
    "ingest_run_id": "r",
    "dataset_id": "PR",
    "notes": "file=PR261106.zip",
    "source_reference_date": date(2026, 11, 6),
}
HEAD = (FIX / "PR261106_BVBG086_head.xml").read_bytes()
TAIL = b"\r\n    </Xchg>\r\n  </BizFileHdr>\r\n</Document>"  # the closing tags of the real file
_START = HEAD.index(b"<BizGrp>")
_OPEN, _CLOSE = HEAD.index(b"<PricRpt>"), HEAD.index(b"</PricRpt>") + len(b"</PricRpt>")
PROLOGUE, WRAPPER, SUFFIX = HEAD[:_START], HEAD[_START:_OPEN], HEAD[_CLOSE:]


def messages(name: str) -> list[tuple[str, bytes]]:
    """(source XML name, byte-exact PricRpt) of an excerpt fixture."""
    text = (FIX / name).read_bytes()
    out, file = [], ""
    for m in re.finditer(rb"<!-- file: ([^ ]+) -->|<PricRpt>\s*<TradDt>.*?</PricRpt>", text, re.S):
        if m.group(1):
            file = m.group(1).decode()
        else:
            out.append((file, m.group(0)))
    return out


def xml(elements: list[bytes], at: str = "2026-11-06T18:39:38", total: int | None = None) -> bytes:
    """A snapshot file: the real prologue (only CreDtAndTm and TtlNbOfMsg changed), one wrapper per message."""
    head = re.sub(rb"<CreDtAndTm>[^<]*</CreDtAndTm>", b"<CreDtAndTm>" + at.encode() + b"</CreDtAndTm>", PROLOGUE)
    n = len(elements) if total is None else total
    head = re.sub(rb"<TtlNbOfMsg>\d+</TtlNbOfMsg>", b"<TtlNbOfMsg>%d</TtlNbOfMsg>" % n, head)
    return head + b"".join(WRAPPER + e + SUFFIX for e in elements) + TAIL


def blob(*files: bytes) -> bytes:
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as z:
        for i, f in enumerate(files):
            z.writestr(f"BVBG.086.01_BV0003282026110603280000018394880{i}.xml", f)
    outer = io.BytesIO()
    with zipfile.ZipFile(outer, "w") as z:
        z.writestr("PR261106.zip", inner.getvalue())
    return outer.getvalue()


def row_of(df: pl.DataFrame, ticker: str, **where: Any) -> dict[str, Any]:
    f = df.filter(pl.col("ticker") == ticker)
    for k, v in where.items():
        f = f.filter(pl.col(k) == v)
    assert f.height == 1
    return f.row(0, named=True)


def test_single_snapshot_values_and_contract() -> None:
    els = [e for _, e in messages("PR261106_BVBG086_excerpt.xml")]
    df = b3_pr.parse_price_report(blob(xml(els)), ROW)
    valid, rejected = b3_pr.PRICE_REPORT.split(df)
    assert rejected.height == 0 and valid.height == df.height == len(els) == 8
    di = row_of(df, "DI1F27")
    assert di["trade_date"] == date(2026, 11, 6) and di["file_date"] == date(2026, 11, 6)
    assert di["b3_instrument_id"] == 409606 and di["trade_count"] == 14025 and di["open_interest"] == 8219135
    assert di["settlement_price"] == Decimal("98087.22") and di["settlement_rate"] == Decimal("13.664")
    assert di["prev_settlement_price"] == Decimal("98087.69") and di["settlement_status"] == "F"
    assert di["volume_brl"] == Decimal("51260388907.12") and di["volume_usd"] == Decimal("9317868305.14")
    assert di["price_ccy"] == "BRL" and di["quantity"] == 522599 and di["settlement_change"] == Decimal("-0.47")
    assert di["snapshot_at"] == datetime(2026, 11, 6, 21, 39, 38, tzinfo=UTC)  # AppHdr CreDt, Z
    assert di["snapshots_seen"] == 1 and di["snapshots_differ"] is False
    assert di["raw_locator"].endswith(";message=1") and di["raw_locator"].startswith("member=BVBG.086.01_")
    assert row_of(df, "DOLZ26")["open_interest"] == 833299 and row_of(df, "DOLZ26")["settlement_price"] == Decimal(
        "5523.964"
    )
    petr = row_of(df, "PETR4")  # a share: no settlement, no open interest
    assert petr["settlement_price"] is None and petr["open_interest"] is None and petr["last_price"] is not None


def test_snapshots_merge_keeps_the_settlement_and_reports_disagreement() -> None:
    first, later = [], []
    for name, el in messages("PR180102_BVBG086_excerpt.xml"):
        (later if name.endswith("1914586047.xml") else first).append(el)
    assert len(first) == 6 and len(later) == 1  # the later snapshot holds INDG18 only
    df = b3_pr.parse_price_report(blob(xml(first, "2018-01-02T18:00:00"), xml(later, "2018-01-02T19:00:00")), ROW)
    assert df.height == 6
    ind = row_of(df, "INDG18")
    assert ind["settlement_price"] == Decimal("78313.0000") and ind["open_interest"] == 369265  # the later one has it
    assert ind["snapshots_seen"] == 2 and ind["snapshots_differ"] is True
    assert row_of(df, "DI1F19")["settlement_price"] == Decimal("93677.51")
    assert row_of(df, "DI1F19")["settlement_rate"] == Decimal("6.805") and row_of(df, "DI1F19")["snapshots_seen"] == 1
    # the same two files in the other order of creation: the order is by header time, not by member name
    swapped = b3_pr.parse_price_report(blob(xml(later, "2018-01-02T19:00:00"), xml(first, "2018-01-02T18:00:00")), ROW)
    assert row_of(swapped, "INDG18")["settlement_price"] == Decimal("78313")
    # a later snapshot without AdjstdQt never replaces one that has it
    no_settle = re.sub(rb"<AdjstdQt .*?</AdjstdQt>", b"", later[0])
    kept = b3_pr.parse_price_report(
        blob(xml(later, "2018-01-02T18:00:00"), xml([no_settle], "2018-01-02T19:00:00")), ROW
    )
    assert row_of(kept, "INDG18")["settlement_price"] == Decimal("78313")


def test_forwards_with_different_terms_are_separate_rows() -> None:
    petr = next(e for _, e in messages("PR261106_BVBG086_excerpt.xml") if b"<TckrSymb>PETR4<" in e)
    # a forward (`...T`) carries one message per term; here the real PETR4 message with a term inserted
    t60 = petr.replace(b"<TradDtls>", b"<TradDtls>\r\n<DaysToSttlm>60</DaysToSttlm>", 1)
    t90 = petr.replace(b"<TradDtls>", b"<TradDtls>\r\n<DaysToSttlm>90</DaysToSttlm>", 1)
    df = b3_pr.parse_price_report(blob(xml([t60, t90])), ROW)
    assert sorted(df["days_to_settlement"].to_list()) == [60, 90] and df["snapshots_seen"].to_list() == [1, 1]


def test_layout_changes_raise() -> None:
    els = [e for _, e in messages("PR261106_BVBG086_excerpt.xml")]
    with pytest.raises(b3_pr.LayoutError, match="declares 9 messages"):
        b3_pr.parse_price_report(blob(xml(els, total=9)), ROW)
    with pytest.raises(b3_pr.LayoutError, match="unknown element"):
        b3_pr.parse_price_report(
            blob(xml([els[0].replace(b"<OpnIntrst>", b"<OpnIntrstX>").replace(b"</OpnIntrst>", b"</OpnIntrstX>")])), ROW
        )
    with pytest.raises(b3_pr.LayoutError, match="more than 2 decimals"):
        b3_pr.parse_price_report(blob(xml([els[0].replace(b"51260388907.12", b"51260388907.123")])), ROW)
    with pytest.raises(b3_pr.LayoutError, match="do not cast"):
        b3_pr.parse_price_report(blob(xml([els[0].replace(b"<OpnIntrst>8219135", b"<OpnIntrst>82x")])), ROW)
    with pytest.raises(b3_pr.LayoutError, match="several currencies"):
        b3_pr.parse_price_report(blob(xml([els[0].replace(b'<LastPric Ccy="BRL">', b'<LastPric Ccy="USD">')])), ROW)
    with pytest.raises(b3_pr.LayoutError, match="identifier scheme"):
        b3_pr.parse_price_report(blob(xml([els[0].replace(b"<Prtry>8</Prtry>", b"<Prtry>9</Prtry>")])), ROW)


def test_connector_routes_pr_and_ignores_empty_download() -> None:
    els = [e for _, e in messages("PR261106_BVBG086_excerpt.xml")]
    out = list(B3PesquisaPregao().parse(blob(xml(els)), ROW))
    assert [p.dataset_id for p in out] == ["price_report"] and out[0].partition == "file_date=2026-11-06"
    assert list(b3_pr.parse_payload(blob(xml(els)), {**ROW, "dataset_id": "TS"})) == []
    assert "price_report" in B3PesquisaPregao.contracts and "swap_rate" in B3PesquisaPregao.contracts
    with pytest.raises(b3_pr.NotData):
        b3_pr.snapshots(b"PK\x05\x06" + b"\x00" * 18)  # the 22-byte empty zip of a day without a file


def test_kept_tzst_holds_the_same_snapshots_and_parses_the_same() -> None:
    b = blob(HEAD, HEAD.replace(b"18:39:38", b"19:16:45"))
    kept, ext, record = b3_pr.extract_snapshots(b)
    assert ext == "tzst" and kept[:4] == b3_pr.ZSTD_MAGIC
    assert sorted(b3_pr.snapshots(kept)) == sorted(b3_pr.snapshots(b))
    assert [m["name"] for m in record["outer"]] == ["PR261106.zip"] and len(record["inner"]) == 2
    assert b3_pr.extract_snapshots(b)[0] == kept  # deterministic: content addressing holds
