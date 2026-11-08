"""CVM RAD versions: the PDFs are stripped from the statements XML, a legacy zip is marked not parsed, and the XML
parses into the open-data `statement_line` contract (periods, scale, DMPL columns, pt-BR numbers)."""

from __future__ import annotations

import io
import json
import random
import zipfile
import zlib
from datetime import date
from decimal import Decimal
from pathlib import Path
from xml.etree import ElementTree as ET

import polars as pl
import pytest

from fin.config import Zones
from fin.ingest import cvm_rad
from fin.ingest.base import Mode, NotData
from fin.ingest.cvm_statements import CONTRACTS
from fin.ingest.http import FetchError

FIX = Path(__file__).parents[1] / "fixtures" / "cvm_rad" / "020800ITR30-09-2024v1.trimmed.xml"
ROW = {"raw_sha256": "b" * 64, "ingest_run_id": "run-1"}
PDF = "JVBERi0xLjQK" * 50  # base64 text of a (fake) PDF


def _zip(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in members.items():
            z.writestr(name, data)
    return buf.getvalue()


def _statements() -> bytes:
    xml = FIX.read_text(encoding="utf-8")
    pdf = f"<A><ImagemObjetoArquivoPdf>{PDF}</ImagemObjetoArquivoPdf></A>"
    return xml.replace("</DadosITR>", pdf + "</DadosITR>").encode()


def test_extract_strips_pdf_text_and_records_the_members() -> None:
    xml = _statements()
    blob = _zip({"020800ITR30-09-2024v1.xml": xml, "142508_020800_x.pdf": b"%PDF" * 100, "DadosDocumento.xlsx": b"x"})
    kept, ext, record = cvm_rad.extract_statements(blob)
    assert ext == "xml" and PDF.encode() not in kept
    assert b"<ImagemObjetoArquivoPdf></ImagemObjetoArquivoPdf>" in kept  # the empty element stays
    assert len(kept) == len(xml) - len(PDF)
    assert record["kept"] == "020800ITR30-09-2024v1.xml" and record["stripped"] == "ImagemObjetoArquivoPdf"
    assert [m["name"] for m in record["members"]] == [
        "020800ITR30-09-2024v1.xml",
        "142508_020800_x.pdf",
        "DadosDocumento.xlsx",
    ]
    assert record["members"][0]["crc32"] == zlib.crc32(xml) and record["members"][0]["size"] == len(xml)
    ET.fromstring(kept)  # still well-formed


def test_extract_refuses_zero_or_two_statements_and_marks_legacy() -> None:
    with pytest.raises(FetchError, match="expected one statements XML"):
        cvm_rad.extract_statements(_zip({"DadosDocumento.xlsx": b"x"}))
    two = _zip({"020800ITR30-09-2024v1.xml": b"<a/>", "020800ITR30-09-2024v2.xml": b"<a/>"})
    with pytest.raises(FetchError, match="expected one statements XML"):
        cvm_rad.extract_statements(two)
    with pytest.raises(FetchError, match="not a zip"):
        cvm_rad.extract_statements(b"<html>busy</html>")
    legacy = _zip({"022497201112310401.dfp": b"PK", "FormularioCadastral.xml": b"<a/>"})
    kept, ext, record = cvm_rad.extract_statements(legacy)
    assert ext == "json" and json.loads(kept) == {"layout": "legacy", "member": "022497201112310401.dfp"}
    assert record["layout"] == "legacy" and record["kept"] is None
    with pytest.raises(NotData):
        list(cvm_rad.parse_payload(kept, ROW))


def _lines() -> pl.DataFrame:
    return cvm_rad.parse_statements(FIX.read_bytes())


def test_lines_follow_the_open_data_contract() -> None:
    frames = [p for p in cvm_rad.parse_payload(FIX.read_bytes(), ROW) if p.dataset_id == "statement_line"]
    lines = pl.concat([p.frame for p in frames])
    good, bad = CONTRACTS["statement_line"].split(lines)
    assert bad.height == 0 and good.height == lines.height > 0
    assert {p.partition for p in frames} >= {
        "form=itr/year=2024/statement=BPA_con",
        "form=itr/year=2024/statement=DRE_con",
        "form=itr/year=2024/statement=DMPL_con",
        "form=itr/year=2024/statement=BPA_ind",
    }
    first = lines.row(0, named=True)
    assert (first["form"], first["cnpj"], first["cd_cvm"]) == ("itr", "02.351.144/0001-18", "020800")
    assert first["version"] == 1 and first["reference_date"] == date(2024, 9, 30)
    assert first["currency"] == "REAL" and first["scale"] == "MIL" and first["raw_sha256"] == ROW["raw_sha256"]


def test_balance_sheet_periods_and_pt_br_numbers() -> None:
    bpa = _lines().filter(pl.col("statement") == "BPA", pl.col("consolidation") == "ind", pl.col("account_code") == "1")
    rows = {r["period_order"]: r for r in bpa.iter_rows(named=True)}
    assert rows["ÚLTIMO"]["value"] == Decimal("1244763") and rows["ÚLTIMO"]["period_end"] == date(2024, 9, 30)
    assert rows["PENÚLTIMO"]["value"] == Decimal("1155954") and rows["PENÚLTIMO"]["period_end"] == date(2023, 12, 31)
    assert rows["ÚLTIMO"]["period_start"] is None and rows["ÚLTIMO"]["fixed_account"] is True
    assert rows["ÚLTIMO"]["statement_group"] == "DF Individual - Balanço Patrimonial Ativo"


def test_q3_income_statement_has_quarter_and_year_to_date() -> None:
    lines = _lines()
    dre = lines.filter(pl.col("statement") == "DRE", pl.col("consolidation") == "con", pl.col("account_code") == "3.01")
    spans = {(r["period_order"], r["period_start"], r["period_end"]) for r in dre.iter_rows(named=True)}
    assert spans == {
        ("ÚLTIMO", date(2024, 7, 1), date(2024, 9, 30)),
        ("ÚLTIMO", date(2024, 1, 1), date(2024, 9, 30)),
        ("PENÚLTIMO", date(2023, 7, 1), date(2023, 9, 30)),
        ("PENÚLTIMO", date(2023, 1, 1), date(2023, 9, 30)),
    }


def test_dmpl_columns_keep_their_own_name() -> None:
    dmpl = _lines().filter(pl.col("statement") == "DMPL", pl.col("consolidation") == "con")
    assert set(dmpl["period_order"]) == {"ÚLTIMO", "PENÚLTIMO"}
    assert set(dmpl["equity_column"]) >= {"Capital Social Integralizado", "Patrimônio Líquido", "Reservas de Lucro"}
    one = dmpl.filter(pl.col("period_order") == "ÚLTIMO", pl.col("equity_column") == "Capital Social Integralizado")
    assert one["period_start"][0] == date(2024, 1, 1) and one["period_end"][0] == date(2024, 9, 30)
    assert one["raw_locator"][0].startswith("Formulario/DfConsolidadas/DemonstracaoMutacoesPatrimonioLiquido/DMPL[1]")


def test_share_counts_as_written() -> None:
    (cap,) = [p for p in cvm_rad.parse_payload(FIX.read_bytes(), ROW) if p.dataset_id == "share_capital"]
    good, bad = CONTRACTS["share_capital"].split(cap.frame)
    assert bad.height == 0 and cap.partition == "form=itr/year=2024"
    row = good.row(0, named=True)
    assert (row["common_paid_in"], row["total_paid_in"], row["common_treasury"]) == (66002915, 66002915, 65143)
    assert row["preferred_treasury"] == 0


def test_numbers_names_and_dates_follow_the_open_data_conventions() -> None:
    assert cvm_rad._value("4,14") == Decimal("4.14") and cvm_rad._value("-7.626.000") == Decimal(-7626000)
    assert cvm_rad._value(" ") is None and cvm_rad._value(None) is None
    with pytest.raises(FetchError):
        cvm_rad._value("1.5")  # neither pt-BR grouping nor a decimal comma: refused, not guessed
    c = ET.fromstring("<Conta><DescricaoConta> a–b\n c  </DescricaoConta></Conta>")
    assert cvm_rad._name(c) == "a-b c  "
    assert cvm_rad._name(ET.fromstring(f"<Conta><DescricaoConta>{'x' * 150}</DescricaoConta></Conta>")) == "x" * 100
    assert cvm_rad._year_before(date(2024, 2, 29)) == date(2023, 2, 28)
    assert cvm_rad._year_before(date(2024, 6, 30)) == date(2023, 6, 30)


def test_discover_asks_for_superseded_versions_not_yet_held(zones: Zones, monkeypatch: pytest.MonkeyPatch) -> None:
    def doc(version: int, doc_id: int, ref: date, cnpj: str = "02.351.144/0001-18") -> dict[str, object]:
        return {
            "form": "itr", "cnpj": cnpj, "reference_date": ref, "version": version, "doc_id": doc_id,
            "company_name": "X", "cd_cvm": "020800", "category": "ITR", "received_on": ref, "link": "-",
        }  # fmt: skip

    index = pl.DataFrame(
        [
            doc(1, 120001, date(2024, 3, 31)),  # superseded, older period: second
            doc(2, 120002, date(2024, 3, 31)),  # latest: open data has it
            doc(1, 130001, date(2024, 9, 30)),  # superseded, newest period: first
            doc(3, 130003, date(2024, 9, 30)),
            doc(2, 130002, date(2024, 9, 30)),  # superseded, held
            doc(1, 100001, date(2021, 3, 31), "1"),  # legacy-layout era: not asked for
            doc(2, 100002, date(2021, 3, 31), "1"),
        ]
    ).with_columns(pl.col("version").cast(pl.Int16), pl.col("doc_id").cast(pl.Int64))
    path = zones.staging / "cvm_dfp_itr" / "document" / "form=itr" / "year=2024" / "a.parquet"
    path.parent.mkdir(parents=True)
    index.write_parquet(path)
    manifest = pl.DataFrame(
        {
            "source_id": ["cvm_rad_versions", "cvm_rad_versions", "other"],
            "http_status": [200, 200, 200],
            "notes": ["doc=130002;itr;v2", None, "doc=120001;itr;v1"],
        }
    )
    monkeypatch.setattr(cvm_rad.Manifest, "read", lambda self: manifest)
    conn = cvm_rad.CvmRadVersions()
    specs = list(conn.discover(Mode.INCREMENTAL, zones))
    assert [s.notes for s in specs] == ["doc=130001;itr;v1", "doc=120001;itr;v1"]
    first = specs[0]
    assert first.url.endswith("NumeroSequencialDocumento=130001") and first.url.startswith(
        "https://www.rad.cvm.gov.br/"
    )
    assert first.extract is cvm_rad.extract_statements and first.conditional is False and first.min_bytes > 1000
    assert conn.concurrency == 4 and conn.min_interval == 0.25 and conn.dedup_staging is False


def test_run_archives_stripped_xml_with_its_record_and_does_not_ask_twice(
    zones: Zones, monkeypatch: pytest.MonkeyPatch
) -> None:
    import httpx

    from fin.ingest import base
    from fin.ingest.http import PoliteClient
    from fin.store.manifest import Manifest
    from fin.store.runs import IngestRun

    index = pl.DataFrame(
        {
            "form": ["itr"] * 4,
            "cnpj": ["02.351.144/0001-18"] * 2 + ["1", "1"],
            "reference_date": [date(2024, 9, 30)] * 2 + [date(2024, 6, 30)] * 2,
            "version": [1, 2, 1, 2],
            "doc_id": [200001, 200002, 200003, 200004],
        },
        schema={
            "form": pl.String,
            "cnpj": pl.String,
            "reference_date": pl.Date,
            "version": pl.Int16,
            "doc_id": pl.Int64,
        },
    )
    path = zones.staging / "cvm_dfp_itr" / "document" / "form=itr" / "year=2024" / "a.parquet"
    path.parent.mkdir(parents=True)
    index.write_parquet(path)
    ok = _zip({"020800ITR30-09-2024v1.xml": _statements(), "x.pdf": b"%PDF" * 5000})
    legacy = _zip({"022497201112310401.dfp": random.Random(1).randbytes(5000), "FormularioCadastral.xml": b"<a/>"})
    asked: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        doc = request.url.params["NumeroSequencialDocumento"]
        asked.append(doc)
        body = ok if doc == "200001" else legacy
        return httpx.Response(200, content=body, headers={"Content-Type": "text/html"})

    monkeypatch.setattr(
        base,
        "PoliteClient",
        lambda **kw: PoliteClient(**kw, transport=httpx.MockTransport(handler), sleep=lambda s: None),
    )
    conn = cvm_rad.CvmRadVersions()
    monkeypatch.setattr(cvm_rad.CvmRadVersions, "min_interval", 0.0)
    monkeypatch.setattr(cvm_rad, "MIN_BYTES", 1000)
    monkeypatch.setattr(cvm_rad, "FIRST_XML_DOC_ID", 0)
    for _ in range(2):
        with IngestRun(zones, "test") as run:
            base.run_connector(conn, zones, run, Mode.INCREMENTAL)
    assert sorted(asked) == ["200001", "200003"]  # the second run found both held
    rows = Manifest(zones.manifest).read().filter(pl.col("source_id") == "cvm_rad_versions")
    assert rows.height == 2 and all(n.startswith("doc=") and ";record=" in n for n in rows["notes"])
    assert sorted(rows["raw_ext"]) == ["json", "xml"]
    staged = list((zones.staging / "cvm_rad_versions").rglob("*.parquet"))
    assert {part for p in staged for part in p.parts} >= {"statement_line", "share_capital"}
