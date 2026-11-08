"""CVM RAD versions: the PDFs are stripped from the statements XML, and the XML parses into the open-data
`statement_line` contract (periods, scale, DMPL columns, pt-BR numbers). A legacy-layout zip keeps its four statement
members and parses into the same contract; one without them is marked unread."""

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

FIXTURES = Path(__file__).parents[1] / "fixtures" / "cvm_rad"
FIX = FIXTURES / "020800ITR30-09-2024v1.trimmed.xml"
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
    unread = _zip({"022497201112310401.dfp": _zip({"Documento.xml": b"<a/>"}), "FormularioCadastral.xml": b"<a/>"})
    kept, ext, record = cvm_rad.extract_statements(unread)
    assert ext == "json" and json.loads(kept) == {"layout": "legacy-unread", "member": "022497201112310401.dfp"}
    assert record["layout"] == "legacy-unread" and record["kept"] is None
    assert [m["name"] for m in record["nested"]["members"]] == ["Documento.xml"]
    with pytest.raises(NotData):
        list(cvm_rad.parse_payload(kept, ROW))
    with pytest.raises(FetchError, match="not a zip"):
        cvm_rad.extract_statements(_zip({"022497201112310401.dfp": b"PK"}))


# --- the legacy layout -----------------------------------------------------------------------------------------


def _legacy_download(did: int, junk: bool = True) -> bytes:
    """A RAD download in the legacy layout from a fixture (real members, InfoFinaDFin cut to a few accounts) plus the
    bulky members that are dropped."""
    nested = {n: (FIXTURES / f"legacy_{did}" / n).read_bytes() for n in cvm_rad.LEGACY_KEPT}
    if junk:
        nested["AnexoDocumento.xml"] = random.Random(1).randbytes(30_000)
        nested["InformacaoFinanceiraDemonstracaoFinanceira.xml"] = b"<A>" + b"<b>1</b>" * 20_000 + b"</A>"
    name = "018112201012310401.dfp" if did == 5110 else "019348202103310301.itr"
    return _zip({name: _zip(nested), "x.pdf": b"%PDF" * 5_000, "FormularioCadastral.xml": b"<a/>"})


def _split(lines: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    return CONTRACTS["statement_line"].split(lines.with_columns(**{k: pl.lit(v) for k, v in ROW.items()}))


def _legacy_kept(did: int) -> bytes:
    return cvm_rad.extract_statements(_legacy_download(did))[0]


def test_legacy_extract_keeps_four_members_byte_for_byte_and_records_the_rest() -> None:
    blob = _legacy_download(5110)
    kept, ext, record = cvm_rad.extract_statements(blob)
    assert ext == "szip" and record["layout"] == "legacy" and kept.startswith(b"PK")
    with zipfile.ZipFile(io.BytesIO(kept)) as z:
        assert z.namelist() == list(cvm_rad.LEGACY_KEPT) and {i.compress_type for i in z.infolist()} == {0}
        for n in cvm_rad.LEGACY_KEPT:
            assert z.read(n) == (FIXTURES / "legacy_5110" / n).read_bytes()
    assert record["kept"] == [f"018112201012310401.dfp/{n}" for n in cvm_rad.LEGACY_KEPT]
    assert record["dropped"] == ["AnexoDocumento.xml", "InformacaoFinanceiraDemonstracaoFinanceira.xml"]
    nested = {m["name"]: m for m in record["nested"]["members"]}
    assert nested["InfoFinaDFin.xml"]["size"] == (FIXTURES / "legacy_5110" / "InfoFinaDFin.xml").stat().st_size
    assert nested["AnexoDocumento.xml"]["crc32"] == zlib.crc32(random.Random(1).randbytes(30_000))
    assert [m["name"] for m in record["members"]] == ["018112201012310401.dfp", "x.pdf", "FormularioCadastral.xml"]
    assert cvm_rad.extract_statements(blob)[0] == kept  # deterministic: the same download, the same object


def test_legacy_lines_follow_the_open_data_contract_and_the_values_of_the_filing() -> None:
    lines, cap = cvm_rad.parse_legacy(_legacy_kept(5110))
    good, bad = _split(lines)
    assert bad.height == 0 and good.height == lines.height == 156
    assert not lines.select(cvm_rad.COLUMNS).is_duplicated().any() and lines["raw_locator"].is_unique().all()
    head = lines.row(0, named=True)
    assert (head["form"], head["cnpj"], head["cd_cvm"], head["version"]) == ("dfp", "02.808.708/0001-07", "018112", 1)
    assert (head["reference_date"], head["currency"], head["scale"]) == (date(2010, 12, 31), "REAL", "MIL")
    bpa = lines.filter(pl.col("statement") == "BPA", pl.col("consolidation") == "ind", pl.col("account_code") == "1")
    rows = {r["period_order"]: r for r in bpa.iter_rows(named=True)}
    assert rows["ÚLTIMO"]["value"] == Decimal("37814986") and rows["PENÚLTIMO"]["value"] == Decimal("35011280")
    assert rows["ÚLTIMO"]["period_start"] is None and rows["ÚLTIMO"]["period_end"] == date(2010, 12, 31)
    assert rows["PENÚLTIMO"]["period_end"] == date(2009, 12, 31) and rows["ÚLTIMO"]["fixed_account"] is True
    assert rows["ÚLTIMO"]["account_name"] == "Ativo Total"
    assert rows["ÚLTIMO"]["statement_group"] == "DF Individual - Balanço Patrimonial Ativo"
    assert rows["ÚLTIMO"]["raw_locator"] == "InfoFinaDFin.xml;id=1;ValorConta1"
    dre = lines.filter(pl.col("statement") == "DRE", pl.col("consolidation") == "con", pl.col("account_code") == "3.01")
    assert {(r["period_order"], r["period_start"]): r["value"] for r in dre.iter_rows(named=True)} == {
        ("ÚLTIMO", date(2010, 1, 1)): Decimal("25233310"),
        ("PENÚLTIMO", date(2009, 1, 1)): Decimal("23194048"),
    }
    assert (cap.height, cap["total_paid_in"][0], cap["common_treasury"][0]) == (1, 3104361, 524)
    prov = {k: pl.lit(v) for k, v in {"raw_locator": "x", **ROW}.items()}
    assert CONTRACTS["share_capital"].split(cap.with_columns(**prov))[1].height == 0


def test_legacy_dmpl_columns_are_positional_like_open_data_and_zeros_are_kept() -> None:
    lines = cvm_rad.parse_legacy(_legacy_kept(5110))[0]
    dmpl = lines.filter(pl.col("statement") == "DMPL", pl.col("account_code") == "5.01")
    con = dmpl.filter(pl.col("consolidation") == "con", pl.col("period_order") == "ÚLTIMO")
    assert con["equity_column"].to_list() == [
        "Capital Social Integralizado",
        "Reservas de Capital, Opções Outorgadas e Ações em Tesouraria",
        "Reservas de Lucro",
        "Lucros ou Prejuízos Acumulados",
        "Outros Resultados Abrangentes",
        "Patrimônio Líquido",
        "Participação dos Não Controladores",
        "Patrimônio Líquido Consolidado",
    ]
    assert con["value"].to_list()[:3] == [Decimal(6832078), Decimal(7771279), Decimal(4771266)]
    ind = dmpl.filter(pl.col("consolidation") == "ind", pl.col("period_order") == "PENÚLTIMO")
    assert ind.height == 6 and ind["period_start"].to_list() == [date(2009, 1, 1)] * 6
    assert ind.filter(pl.col("equity_column") == "Lucros ou Prejuízos Acumulados")["value"][0] == 0  # a zero is a line
    zero = lines.filter(  # an all-zero account of the filing
        pl.col("statement") == "DMPL",
        pl.col("consolidation") == "con",
        pl.col("period_order") == "ÚLTIMO",
        pl.col("account_code") == "5.02",
    )
    assert zero.height == 8 and set(zero["value"]) == {Decimal(0)}


def test_legacy_itr_has_quarter_and_year_to_date_and_extra_dmpl_columns() -> None:
    lines, cap = cvm_rad.parse_legacy(_legacy_kept(103318))
    assert _split(lines)[1].height == 0
    assert lines["form"][0] == "itr" and lines["reference_date"][0] == date(2021, 3, 31)
    dre = lines.filter(pl.col("statement") == "DRE", pl.col("consolidation") == "con", pl.col("account_code") == "3.01")
    assert {(r["period_order"], r["period_start"], r["period_end"]) for r in dre.iter_rows(named=True)} == {
        ("ÚLTIMO", date(2021, 1, 1), date(2021, 3, 31)),
        ("PENÚLTIMO", date(2020, 1, 1), date(2020, 3, 31)),
    }  # a Q1 quarter is the year to date: one span each
    bpa = lines.filter(pl.col("statement") == "BPA", pl.col("consolidation") == "ind", pl.col("account_code") == "1")
    assert {(r["period_order"], r["period_end"]) for r in bpa.iter_rows(named=True)} == {
        ("ÚLTIMO", date(2021, 3, 31)),
        ("PENÚLTIMO", date(2020, 12, 31)),
    }  # the previous year's balance is the previous fiscal year end
    ind = lines.filter(
        pl.col("statement") == "DMPL", pl.col("consolidation") == "ind", pl.col("period_order") == "ÚLTIMO"
    )
    assert ind.filter(pl.col("account_code") == "5.01").height == 7  # this filing's individual DMPL has 7 columns
    assert cap["preferred_treasury"][0] == 24476


def test_legacy_zero_period_is_kept_when_a_sibling_statement_has_values() -> None:
    def rec(i: int, stmt: str, values: tuple[str, str]) -> str:
        v = "".join(f"<ValorConta{n}>{x}</ValorConta{n}>" for n, x in enumerate(values, start=1))
        return (
            f"<InfoFinaDFin><NumeroIdentificadorInfoFinaDFin>{i}</NumeroIdentificadorInfoFinaDFin>"
            "<PeriodoDemonstracaoFinanceira><NumeroIdentificacaoPeriodo>0</NumeroIdentificacaoPeriodo>"
            "</PeriodoDemonstracaoFinanceira><PlanoConta><VersaoPlanoConta>"
            f"<CodigoTipoDemonstracaoFinanceira>{stmt}</CodigoTipoDemonstracaoFinanceira>"
            "<CodigoTipoInformacaoFinanceira>2</CodigoTipoInformacaoFinanceira></VersaoPlanoConta>"
            f"<NumeroConta>{i}.01</NumeroConta><IndicadorContaFixa>false</IndicadorContaFixa></PlanoConta>"
            f"<DescricaoConta1>Conta {i}</DescricaoConta1>{v}</InfoFinaDFin>"
        )

    src = FIXTURES / "legacy_5110"
    info = "<ArrayOfInfoFinaDFin>" + rec(1, "4", ("5", "6")) + rec(2, "5", ("0", "0")) + "</ArrayOfInfoFinaDFin>"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n in cvm_rad.LEGACY_KEPT:
            z.writestr(n, info if n == "InfoFinaDFin.xml" else (src / n).read_bytes())
    lines = cvm_rad.parse_legacy(buf.getvalue())[0]
    dra = lines.filter(pl.col("statement") == "DRA")  # all zero, but the DRE next to it reports both periods
    assert dra.height == 2 and set(dra["value"]) == {Decimal(0)} and lines.height == 4


def test_legacy_payload_dispatch_partitions_and_provenance() -> None:
    parts = list(cvm_rad.parse_payload(_legacy_kept(5110), ROW))
    names = {(p.dataset_id, p.partition) for p in parts}
    assert ("statement_line", "form=dfp/year=2010/statement=DMPL_con") in names
    assert ("share_capital", "form=dfp/year=2010") in names
    cap = next(p for p in parts if p.dataset_id == "share_capital").frame
    assert cap["raw_locator"][0].startswith("legacy;") and cap["raw_sha256"][0] == ROW["raw_sha256"]
    assert all(p.frame["ingest_run_id"][0] == "run-1" for p in parts)


def test_legacy_refuses_a_payload_that_is_not_what_extract_wrote() -> None:
    with pytest.raises(FetchError, match="not a zip"):
        cvm_rad.parse_legacy(b"PKnot a zip")
    with pytest.raises(FetchError, match="lacks"):
        cvm_rad.parse_legacy(_zip({"Documento.xml": b"<a/>"}))


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
            doc(1, 100001, date(2021, 3, 31), "1"),  # legacy layout, held as a marker of version 1: asked again
            doc(2, 100002, date(2021, 3, 31), "1"),
            doc(1, 90001, date(2020, 3, 31), "1"),  # legacy layout, a marker or a stored payload of version 2: held
            doc(2, 90002, date(2020, 3, 31), "1"),
            doc(1, 80001, date(2019, 3, 31), "1"),  # legacy layout read by version 1? it stored a payload: held
            doc(2, 80002, date(2019, 3, 31), "1"),
        ]
    ).with_columns(pl.col("version").cast(pl.Int16), pl.col("doc_id").cast(pl.Int64))
    path = zones.staging / "cvm_dfp_itr" / "document" / "form=itr" / "year=2024" / "a.parquet"
    path.parent.mkdir(parents=True)
    index.write_parquet(path)
    rows = [  # (source, notes, raw_ext, connector_version)
        ("cvm_rad_versions", "doc=130002;itr;v2", "xml", "1"),
        ("cvm_rad_versions", None, "json", "1"),
        ("cvm_rad_versions", "doc=100001;itr;v1", "json", "1"),  # a legacy marker of the connector that did not read it
        ("cvm_rad_versions", "doc=90001;itr;v1", "json", "2"),
        ("cvm_rad_versions", "doc=80001;itr;v1", "xml", "1"),
        ("other", "doc=120001;itr;v1", "xml", "1"),
    ]
    manifest = pl.DataFrame(
        {k: [r[i] for r in rows] for i, k in enumerate(("source_id", "notes", "raw_ext", "connector_version"))}
    ).with_columns(http_status=pl.lit(200))
    monkeypatch.setattr(cvm_rad.Manifest, "read", lambda self: manifest)
    conn = cvm_rad.CvmRadVersions()
    specs = list(conn.discover(Mode.INCREMENTAL, zones))
    assert [s.notes for s in specs] == ["doc=130001;itr;v1", "doc=120001;itr;v1", "doc=100001;itr;v1"]
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
            "form": ["itr"] * 6,
            "cnpj": ["02.351.144/0001-18"] * 2 + ["1", "1", "2", "2"],
            "reference_date": [date(2024, 9, 30)] * 2 + [date(2024, 6, 30)] * 2 + [date(2010, 12, 31)] * 2,
            "version": [1, 2, 1, 2, 1, 2],
            "doc_id": [200001, 200002, 200003, 200004, 200005, 200006],
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
    unread = _zip(
        {"022497201112310401.dfp": _zip({"Documento.xml": b"<a/>"}), "x.pdf": random.Random(2).randbytes(3000)}
    )
    legacy = _legacy_download(5110)
    asked: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        doc = request.url.params["NumeroSequencialDocumento"]
        asked.append(doc)
        body = {"200001": ok, "200003": unread, "200005": legacy}[doc]
        return httpx.Response(200, content=body, headers={"Content-Type": "text/html"})

    monkeypatch.setattr(
        base,
        "PoliteClient",
        lambda **kw: PoliteClient(**kw, transport=httpx.MockTransport(handler), sleep=lambda s: None),
    )
    conn = cvm_rad.CvmRadVersions()
    monkeypatch.setattr(cvm_rad.CvmRadVersions, "min_interval", 0.0)
    monkeypatch.setattr(cvm_rad, "MIN_BYTES", 1000)
    for _ in range(2):
        with IngestRun(zones, "test") as run:
            base.run_connector(conn, zones, run, Mode.INCREMENTAL)
    assert sorted(asked) == ["200001", "200003", "200005"]  # the second run found all held
    rows = Manifest(zones.manifest).read().filter(pl.col("source_id") == "cvm_rad_versions")
    assert rows.height == 3 and all(n.startswith("doc=") and ";record=" in n for n in rows["notes"])
    assert sorted(rows["raw_ext"]) == ["json", "szip", "xml"] and set(rows["connector_version"]) == {"2"}
    staged = list((zones.staging / "cvm_rad_versions").rglob("*.parquet"))
    assert {part for p in staged for part in p.parts} >= {"statement_line", "share_capital"}
    assert any("year=2010" in p.parts for p in staged)  # the legacy payload was parsed too
