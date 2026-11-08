"""CVM RAD: the superseded versions of DFP/ITR filings (docs/sources/cvm_rad_versions.md).

CVM's open-data DFP/ITR zips keep only the latest version of each filing (docs/sources/cvm_dfp_itr.md). RAD, the
filing system, still serves every version as a zip (`frmDownloadDocumento.aspx?...NumeroSequencialDocumento=<ID_DOC>`).
Its statements XML (`<CVM6><DFP|ITR><dd-mm-yyyy>v<N>.xml`) is 60 % base64 PDF; the PDF text is stripped before the
object is archived (ADR-0027) and the XML is parsed into exactly the open-data `statement_line` contract, so a
superseded version and the latest one are rows of one table that differ only in `version` and the numbers.

Filings up to October 2021 come in a legacy layout instead (a nested `.dfp`/`.itr` zip of entity dumps, 30 to 80 MB
of XML): four of its members hold the statements and are kept as they are, the rest (PDF, notes, a 40 MB verbose
duplicate) is dropped; `parse_legacy` reads them into the same contract.

Only the statements are read. `Documento/ResponsavelDocumento` (the filer's name, phone, e-mail) is never parsed.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from collections.abc import Iterable
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, ClassVar
from xml.etree import ElementTree as ET

import polars as pl

from fin.config import Zones
from fin.ingest.base import Connector, Mode, NotData, Parsed
from fin.ingest.cvm_statements import SHARE_CAPITAL, STATEMENT_LINE, VALUE
from fin.ingest.fetch import FetchSpec
from fin.ingest.http import FetchError
from fin.schema import Contract
from fin.store.manifest import Manifest
from fin.store.tables import read_parquet_dir

# the date may carry a time ("027251DFP31-12-2025 00_00_00v2.xml", measured 2026-11-08)
STATEMENTS_MEMBER = re.compile(r"^\d{6}(?:DFP|ITR)\d{2}-\d{2}-\d{4}(?: \d{2}_\d{2}_\d{2})?v\d+\.xml$", re.IGNORECASE)
URL = "https://www.rad.cvm.gov.br/ENETCONSULTA/frmDownloadDocumento.aspx?CodigoInstituicao=1&NumeroSequencialDocumento={doc_id}"
MIN_BYTES = 100_000  # RAD answers 200 with a ~300-byte HTML stub when it is busy: absent now, tried again next run
_DOC = re.compile(r"doc=(\d+)")
_NUMBER = re.compile(r"^-?(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d+)?$")
LEGACY_MEMBER = re.compile(r"^\d{18}\.(?:dfp|itr)$", re.IGNORECASE)
# the members of the nested legacy zip that hold the statements; the rest of it is dropped (`extract_legacy`)
LEGACY_KEPT = (
    "Documento.xml",
    "PeriodoDemonstracaoFinanceira.xml",
    "ComposicaoCapitalSocialDemonstracaoFinanceiraNegocios.xml",
    "InfoFinaDFin.xml",
)
# RAD served a nested legacy zip (`.dfp`/`.itr` of entity dumps) up to doc 108885 (2021-10-04) and the statements XML
# from doc 108951 (2021-10-07), and a few later documents (re-presentations of old periods) still in the legacy layout.
# The connector reads the legacy layout from version 2; a JSON marker stored by version 1 is a legacy filing that
# was not read, and is fetched again.
LEGACY_READER = 2
_PDF = re.compile(rb"(<ImagemObjetoArquivoPdf(?:\s[^>]*)?>)[^<]*(</ImagemObjetoArquivoPdf>)")


class RadError(FetchError):
    """A RAD download or statements XML that is not what this module reads. A `FetchError`, so a run records it and
    goes on with the next document."""

    def __init__(self, message: str) -> None:
        super().__init__("cvm_rad", message)


def extract_statements(blob: bytes) -> tuple[bytes, str, dict[str, Any]]:
    """What is kept of a RAD download: the statements XML without its embedded PDFs (the base64 text of every
    `<ImagemObjetoArquivoPdf>`; the empty element stays), or, for a filing in the legacy layout, the members of its
    nested zip that hold the statements (`extract_legacy`)."""
    try:
        z = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile as e:
        raise RadError(f"not a zip: {e}") from e
    infos = [i for i in z.infolist() if not i.is_dir()]
    members = [{"name": i.filename, "size": i.file_size, "crc32": i.CRC} for i in infos]
    hits = [i for i in infos if STATEMENTS_MEMBER.match(i.filename)]
    legacy = [i for i in infos if LEGACY_MEMBER.match(i.filename)]
    if not hits and len(legacy) == 1:
        return extract_legacy(z.read(legacy[0]), legacy[0].filename, members)
    if len(hits) != 1:
        raise RadError(
            f"expected one statements XML, found {[i.filename for i in hits]} among {[i.filename for i in infos]}"
        )
    xml = z.read(hits[0])  # raises on a CRC mismatch
    kept = _PDF.sub(rb"\1\2", xml)
    return kept, "xml", {"members": members, "kept": hits[0].filename, "stripped": "ImagemObjetoArquivoPdf"}


def extract_legacy(nested: bytes, name: str, members: list[dict[str, Any]]) -> tuple[bytes, str, dict[str, Any]]:
    """The legacy layout: `nested` is the `<CVM6><year><period>.dfp|.itr` zip of entity dumps. Four of its members
    (`LEGACY_KEPT`, 0.1 % of the zip) hold every number of the statements and are kept byte for byte, in a stored
    (uncompressed, fixed-date) zip so that the raw store's own compression and deltas apply. Dropped: the PDF and
    annexes, the notes, and `InformacaoFinanceiraDemonstracaoFinanceira.xml`, a 30 to 80 MB duplicate of
    `InfoFinaDFin.xml` that repeats the filing's header in every cell. A nested zip without those four members is
    marked `legacy-unread` (JSON), so it counts as held and shows up in the not-data counts."""
    try:
        z = zipfile.ZipFile(io.BytesIO(nested))
    except zipfile.BadZipFile as e:
        raise RadError(f"legacy member {name} is not a zip: {e}") from e
    infos = {i.filename: i for i in z.infolist() if not i.is_dir()}
    listing = [{"name": n, "size": i.file_size, "crc32": i.CRC} for n, i in infos.items()]
    record: dict[str, Any] = {"members": members, "layout": "legacy", "nested": {"member": name, "members": listing}}
    if any(n not in infos for n in LEGACY_KEPT):
        marker = json.dumps({"layout": "legacy-unread", "member": name}).encode("utf-8")
        return marker, "json", {**record, "kept": None, "layout": "legacy-unread"}
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as k:
        for n in LEGACY_KEPT:
            k.writestr(zipfile.ZipInfo(n, date_time=(1980, 1, 1, 0, 0, 0)), z.read(infos[n]))  # CRC checked on read
    record["kept"] = [f"{name}/{n}" for n in LEGACY_KEPT]
    record["dropped"] = [n for n in infos if n not in LEGACY_KEPT]
    return out.getvalue(), "szip", record


# --- the statements XML -> the open-data `statement_line` contract ----------------------------------------------

_SCALE = {"1": "UNIDADE", "2": "MIL"}
_CURRENCY = {"1": "REAL"}
_STATEMENT_ELEMENTS = {
    "BalancoPatrimonialAtivo": "BPA",
    "BalancoPatrimonialPassivo": "BPP",
    "DemonstracaoResultado": "DRE",
    "DemonstracaoResultadoAbrangente": "DRA",
    "DemonstracaoFluxoCaixa": "DFC",
    "DemonstracaoMutacoesPatrimonioLiquido": "DMPL",
    "DemonstracaoValorAdicionado": "DVA",
}
_GROUP_NAMES = {
    "BPA": "Balanço Patrimonial Ativo",
    "BPP": "Balanço Patrimonial Passivo",
    "DRE": "Demonstração do Resultado",
    "DRA": "Demonstração de Resultado Abrangente",
    "DFC_MD": "Demonstração do Fluxo de Caixa (Método Direto)",
    "DFC_MI": "Demonstração do Fluxo de Caixa (Método Indireto)",
    "DMPL": "Demonstração das Mutações do Patrimônio Líquido",
    "DVA": "Demonstração de Valor Adicionado",
}
_DFC_METHOD = {"Direto": "DFC_MD", "Indireto": "DFC_MI"}
_FORMS = {"DadosDFP": "dfp", "DadosITR": "itr"}
# DMPL column element -> the open-data COLUNA_DF label. Open data labels the Nth column of the XML with the Nth label
# of its fixed list, so a filing whose columns differ from that list (an extra ReservasReavaliacao, or
# AjustesAvaliacaoPatrimonial before LucroPrejuizoAcumulado) is mislabelled there; here a column keeps its own name.
_EQUITY = {
    "CapitalSocialIntegralizado": "Capital Social Integralizado",
    "ReservasCapital": "Reservas de Capital, Opções Outorgadas e Ações em Tesouraria",
    "ReservasCapitalOpcoesOutorgAcoesTesour": "Reservas de Capital, Opções Outorgadas e Ações em Tesouraria",
    "ReservasReavaliacao": "Reservas de Reavaliação",
    "ReservasLucro": "Reservas de Lucro",
    "LucroPrejuizoAcumulado": "Lucros ou Prejuízos Acumulados",
    "AjustesAvaliacaoPatrimonial": "Ajustes de Avaliação Patrimonial",
    "OutrosResultadosAbrangentes": "Outros Resultados Abrangentes",
    "PatrimonioLiquido": "Patrimônio Líquido",
    "PatrimonioLiquidoAcionistasControl": "Patrimônio Líquido",
    "PatrimonioLiquidoAcionistasNaoControl": "Participação dos Não Controladores",
    "PatrimonioLiquidoConsolidado": "Patrimônio Líquido Consolidado",
}
# the same columns when the XML spells them out (`DadosContas/CamposDadosContas/Descricao`): prefix -> label
_EQUITY_TEXT = (
    ("capital social", "Capital Social Integralizado"),
    ("reservas de capital", _EQUITY["ReservasCapital"]),
    ("reservas de reavalia", _EQUITY["ReservasReavaliacao"]),
    ("reservas de lucro", "Reservas de Lucro"),
    ("lucros ou preju", "Lucros ou Prejuízos Acumulados"),
    ("lucros/preju", "Lucros ou Prejuízos Acumulados"),
    ("ajustes de avalia", _EQUITY["AjustesAvaliacaoPatrimonial"]),
    ("outros resultados abrangentes", "Outros Resultados Abrangentes"),
    ("participa", "Participação dos Não Controladores"),
    ("patrimônio líquido consolidado", "Patrimônio Líquido Consolidado"),
    ("patrimônio líquido", "Patrimônio Líquido"),
)
_EPS_HEADERS = ("3.99", "3.99.01", "3.99.02")  # empty in the XML, 0 in open data
NAME_WIDTH = 100  # open data cuts DS_CONTA at 100 characters; the archived XML keeps the full text
_BALANCE_TAGS = ("UltimoExercicio", "PenultimoExercicio", "TrimestreAtual", "ExercicioAnterior")
_META = ("ContaFixa", "CodigoConta", "DescricaoConta", "Metodo")

COLUMNS = [  # the open-data `statement_line` columns, then the locator of the line in the XML
    *("form", "cnpj", "reference_date", "version", "company_name", "cd_cvm", "statement", "consolidation"),
    *("statement_group", "currency", "scale", "period_order", "period_start", "period_end", "equity_column"),
    *("account_code", "account_name", "value", "fixed_account", "raw_locator"),
]
SCHEMA: dict[str, Any] = {
    **dict.fromkeys(COLUMNS, pl.String),
    "reference_date": pl.Date,
    "version": pl.Int16,
    "period_start": pl.Date,
    "period_end": pl.Date,
    "value": VALUE,
    "fixed_account": pl.Boolean,
}

Period = tuple[str, date | None, date]  # (period_order, start, end)


def _day(text: str | None) -> date | None:
    if text is None or not text.strip():
        return None
    d, m, y = text.strip().split()[0].split("/")  # some filings write "31/12/2025 00:00:00"
    return date(int(y), int(m), int(d))


def _year_before(d: date) -> date:
    """The prior-year counterpart of a period boundary: a month end stays a month end (29 Feb -> 28 Feb)."""
    month_end = (d + timedelta(days=1)).month != d.month
    try:
        out = d.replace(year=d.year - 1)
    except ValueError:
        out = d.replace(year=d.year - 1, day=28)
    if month_end:
        out = (out.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    return out


def _placeholder(c: ET.Element, v: Decimal) -> bool:
    """An unused slot of the CVM template: no description and a zero (open data omits them)."""
    return v == 0 and not _text(c, "DescricaoConta")


def _eps_headers(contas: list[ET.Element]) -> set[str]:
    """The EPS headings (3.99, 3.99.01, 3.99.02) of a DRE that have a priced line below them: their value element
    is empty in the XML and open data carries them as 0 (a heading with nothing below stays absent)."""
    priced = {
        _text(c, "CodigoConta") or "" for c in contas if any((x.text or "").strip() for x in c if x.tag not in _META)
    }
    return {h for h in _EPS_HEADERS if any(code.startswith(h + ".") for code in priced)}


def _cnpj(digits: str) -> str:
    d = digits.strip().zfill(14)
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


def _text(e: ET.Element | None, tag: str) -> str | None:
    c = None if e is None else e.find(tag)
    return None if c is None or c.text is None else c.text.strip()


def _value(text: str | None) -> Decimal | None:
    """A number as the XML writes it, pt-BR: an optional decimal comma, and dots grouping thousands when the filer
    typed them (`-7.626.000`, found in any statement). Anything else is an error, never a guess."""
    if text is None or not text.strip():
        return None
    t = text.strip()
    if not _NUMBER.match(t):
        raise RadError(f"unparseable value {text!r}")
    return Decimal(t.replace(".", "").replace(",", "."))


def _periods(data: ET.Element, form: str) -> dict[str, Period]:
    """The period each value element of a statement reports: tag -> (period_order, start, end)."""

    def need(tag: str) -> date:
        d = _day(_text(data, tag))
        if d is None:
            raise RadError(f"{tag} missing")
        return d

    if form == "dfp":
        return {
            "UltimoExercicio": ("ÚLTIMO", need("DtInicioUltimoExercicioSocial"), need("DtFimUltimoExercicioSocial")),
            "PenultimoExercicio": (
                "PENÚLTIMO",
                need("DtInicioPenultimoExercicioSocial"),
                need("DtFimPenultimoExercicioSocial"),
            ),
        }
    q0, q1 = need("DtInicioTrimestreAtual"), need("DtFimTrimestreAtual")
    y0, py0 = need("DtInicioExercicioSocialCurso"), need("DtInicioExercicioSocialAnterior")
    return {
        "TrimestreAtual": ("ÚLTIMO", q0, q1),
        "AcumuladoExercicioAtual": ("ÚLTIMO", y0, q1),
        "AcumuladoAtualExercicio": ("ÚLTIMO", y0, q1),
        "TrimestreAnterior": ("PENÚLTIMO", _year_before(q0), _year_before(q1)),
        "AcumuladoExercicioAnterior": ("PENÚLTIMO", py0, _year_before(q1)),
        "ExercicioAnterior": ("PENÚLTIMO", None, need("DtFimExercicioSocialAnterior")),
    }


def parse_statements(xml: bytes) -> pl.DataFrame:
    """The account lines of a RAD statements XML (PDFs stripped) as the open-data `statement_line` contract."""
    root = ET.fromstring(xml)
    company, doc = root.find("DadosEmpresa"), root.find("Documento")
    found = [(f, e) for t, f in _FORMS.items() if (e := root.find(t)) is not None]
    if company is None or doc is None or len(found) != 1:
        raise RadError("not a DFP/ITR statements XML")
    form, data = found[0]
    reference = _day(_text(data, "DataReferencia"))
    scale = _SCALE.get(_text(data, "EscalaMoeda") or "")
    currency = _CURRENCY.get(_text(data, "Moeda") or "")
    if reference is None or scale is None or currency is None:
        raise RadError(f"unknown reference/scale/currency: {_text(data, 'EscalaMoeda')} {_text(data, 'Moeda')}")
    periods = _periods(data, form)
    head: dict[str, Any] = {
        "form": form,
        "cnpj": _cnpj(_text(company, "CnpjEmpresa") or ""),
        "reference_date": reference,
        "version": int(_text(doc, "VersaoDocumento") or ""),
        "company_name": _text(company, "RazaoSocialEmpresa"),
        "cd_cvm": (_text(company, "CodigoCvm") or "").zfill(6),
        "currency": currency,
        "scale": scale,
    }
    forms = data.find("Formulario")
    if forms is None:
        raise RadError("no Formulario")
    rows: list[dict[str, Any]] = []
    for container, cons in (("DfConsolidadas", "con"), ("DfIndividuais", "ind")):
        group = forms.find(container)
        for st in () if group is None else group:
            code = _STATEMENT_ELEMENTS.get(st.tag)
            if code is None:
                raise RadError(f"unknown statement element {st.tag}")
            where = f"Formulario/{container}/{st.tag}"
            if code == "DMPL":
                _dmpl(st, rows, head, cons, periods, where)
                continue
            balance = code in ("BPA", "BPP")
            contas = st.findall("Conta")
            eps = _eps_headers(contas) if code == "DRE" else set()
            for n, c in enumerate(contas, start=1):
                stmt = code
                if code == "DFC":
                    method = _text(c, "Metodo")
                    if method not in _DFC_METHOD:
                        raise RadError(f"DFC method {method!r}")
                    stmt = _DFC_METHOD[method]
                heading = _text(c, "CodigoConta") in eps and bool(_text(c, "DescricaoConta"))
                values: dict[Period, Decimal] = {}  # a Q1 quarter is also the year to date: one line, the written value
                for tag, (order, start, end) in periods.items():
                    if tag not in _BALANCE_TAGS if balance else tag == "ExercicioAnterior":
                        continue
                    v = _value(_text(c, tag))
                    span = (order, None if balance else start, end)
                    if v is None and heading and c.find(tag) is not None:
                        v = Decimal(0)  # only if no other element of the span has a value
                        values.setdefault(span, v)
                    elif v is not None and not _placeholder(c, v) and (span not in values or values[span] == 0):
                        values[span] = v
                for span, v in values.items():
                    rows.append(_line(head, c, stmt, cons, span, None, v, f"{where}/Conta[{n}]"))
    return pl.DataFrame(rows, schema=SCHEMA) if rows else pl.DataFrame(schema=SCHEMA)


_DS_CONTA = {ord("\r"): None, ord("\n"): None, ord("\t"): None, 0x2013: "-"}  # measured against open data


def _name(c: ET.Element) -> str | None:
    """DS_CONTA as the open-data CSV writes it (measured): spaces stripped, then line breaks and tabs removed (so a
    space before a break survives), a no-break space kept, an en dash written as a hyphen, cut at `NAME_WIDTH`."""
    e = c.find("DescricaoConta")
    return _clean_name(None if e is None else e.text)


def _clean_name(raw: str | None) -> str | None:
    text = "" if raw is None else raw.strip(" ")
    return text.translate(_DS_CONTA)[:NAME_WIDTH] or None


def _line(
    head: dict[str, Any],
    c: ET.Element,
    stmt: str,
    cons: str,
    period: Period,
    equity: str | None,
    v: Decimal,
    locator: str,
) -> dict[str, Any]:
    fixed = _text(c, "ContaFixa")
    return {
        **head,
        "statement": stmt,
        "consolidation": cons,
        "statement_group": ("DF Consolidado - " if cons == "con" else "DF Individual - ") + _GROUP_NAMES[stmt],
        "period_order": period[0],
        "period_start": period[1],
        "period_end": period[2],
        "equity_column": equity,
        "account_code": _text(c, "CodigoConta"),
        "account_name": _name(c),
        "value": v,
        "fixed_account": {"True": True, "False": False}.get(fixed or ""),
        "raw_locator": locator,
    }


def _dmpl(
    st: ET.Element,
    rows: list[dict[str, Any]],
    head: dict[str, Any],
    cons: str,
    periods: dict[str, Period],
    where: str,
) -> None:
    """DMPL: one `<DMPL>` block per period, one column per equity component of each account (an element each, or a
    `CamposDadosContas` entry with its label)."""
    by_span = {(p[1], p[2]): p for t, p in periods.items() if t not in ("TrimestreAtual", "TrimestreAnterior")}
    for b, block in enumerate(st.findall("DMPL"), start=1):
        per = block.find("Periodo")
        span = (_day(_text(per, "DtInicio")), _day(_text(per, "DtFim")))
        period = by_span.get(span)  # type: ignore[arg-type]
        if period is None:  # the antepenultimate period: not part of the open-data layout
            continue
        for n, c in enumerate(block.findall("Contas/Conta"), start=1):
            at = f"{where}/DMPL[{b}]/Contas/Conta[{n}]"
            columns: list[tuple[str, str | None, str]] = []  # (label, value text, locator)
            for col in c:
                if col.tag in _META:
                    continue
                if col.tag == "DadosContas":
                    for k, f in enumerate(col.findall("CamposDadosContas"), start=1):
                        label = _equity_label(_text(f, "Descricao") or "")
                        columns.append((label, _text(f, "Valor"), f"{at}/DadosContas[{k}]"))
                    continue
                label = _EQUITY.get(col.tag)
                if label is None:
                    raise RadError(f"unknown DMPL column {col.tag}")
                columns.append((label, col.text, f"{at}/{col.tag}"))
            for label, text, locator in columns:
                v = _value(text)
                if v is not None and not _placeholder(c, v):
                    rows.append(_line(head, c, "DMPL", cons, period, label, v, locator))


def _equity_label(text: str) -> str:
    t = re.sub(r"\s*/\s*", "/", text.strip().casefold()).replace("lucro/", "lucros/")  # "Lucro / Prejuízo"
    for prefix, label in _EQUITY_TEXT:
        if t.startswith(prefix):
            return label
    raise RadError(f"unknown DMPL column {text!r}")


_CAPITAL = {"common": "Ordinarias", "preferred": "Preferenciais", "total": "QtdeTotalAcoes"}


def parse_capital(xml: bytes) -> pl.DataFrame:
    """`ComposicaoCapital` (shares paid in and in treasury) as the open-data `share_capital` contract: the counts as
    written, which are in thousands when `EscalaQtdAcoes` is 2, exactly as open data carries them."""
    root = ET.fromstring(xml)
    found = [(f, e) for t, f in _FORMS.items() if (e := root.find(t)) is not None]
    company, doc = root.find("DadosEmpresa"), root.find("Documento")
    if company is None or doc is None or len(found) != 1:
        raise RadError("not a DFP/ITR statements XML")
    form, data = found[0]
    comp = data.find("Formulario/DadosEmpresa/ComposicaoCapital")
    if comp is None:
        return pl.DataFrame(schema=CAPITAL_SCHEMA)
    out: dict[str, Any] = {
        "form": form,
        "cnpj": _cnpj(_text(company, "CnpjEmpresa") or ""),
        "reference_date": _day(_text(data, "DataReferencia")),
        "version": int(_text(doc, "VersaoDocumento") or ""),
        "company_name": _text(company, "RazaoSocialEmpresa"),
    }
    for a, tag in (("paid_in", "CaptalIntegralizado"), ("treasury", "Tesouraria")):
        for b, el in _CAPITAL.items():
            v = _value(_text(comp, f"{tag}/{el}"))
            # open data carries a missing treasury count as 0
            out[f"{b}_{a}"] = int(v) if v is not None else (0 if a == "treasury" else None)
    return pl.DataFrame([out], schema=CAPITAL_SCHEMA)


CAPITAL_SCHEMA: dict[str, Any] = {
    "form": pl.String,
    "cnpj": pl.String,
    "reference_date": pl.Date,
    "version": pl.Int16,
    "company_name": pl.String,
    **{f"{b}_{a}": pl.Int64 for b in _CAPITAL for a in ("paid_in", "treasury")},
}


# --- the legacy layout (`extract_legacy`) -> the same contract ----------------------------------------------------
# `InfoFinaDFin.xml` has one record per account line: `PlanoConta/NumeroConta`, the statement and consolidation
# codes of `PlanoConta/VersaoPlanoConta`, `DescricaoConta1`, `IndicadorContaFixa` and `ValorConta1..12`. Except in
# the DMPL, `ValorContaN` is the value for period id N of `PeriodoDemonstracaoFinanceira.xml`; a DMPL record carries
# its period id in its own `PeriodoDemonstracaoFinanceira`, and `ValorContaN` is equity column N. The zip labels
# neither the statements nor the DMPL columns: the codes below were matched against open data.

_LEGACY_STATEMENT = {
    "2": "BPA",
    "3": "BPP",
    "4": "DRE",
    "5": "DRA",
    "6": "DFC_MD",
    "7": "DFC_MI",
    "8": "DMPL",
    "9": "DVA",
}
_LEGACY_CONSOLIDATION = {"1": "ind", "2": "con"}
_LEGACY_FORM = {"3": "itr", "4": "dfp"}
# DMPL column N is labelled as open data labels it: the Nth entry of a fixed list (a filing whose columns differ from
# the list is mislabelled there, and so here: the zip does not say what its columns are)
_LEGACY_EQUITY = (
    "Capital Social Integralizado",
    _EQUITY["ReservasCapital"],
    "Reservas de Lucro",
    "Lucros ou Prejuízos Acumulados",
    "Outros Resultados Abrangentes",
    "Patrimônio Líquido",
    "Participação dos Não Controladores",
    "Patrimônio Líquido Consolidado",
)
_ISO_DAY = re.compile(r"^(\d{4})-(\d{2})-(\d{2})T")
_LEGACY_VALUES = 12


def _iso_day(text: str | None) -> date | None:
    m = _ISO_DAY.match(text or "")
    if m is None or m.group(1) == "0001":
        return None
    return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))


def _legacy_members(blob: bytes) -> dict[str, bytes]:
    try:
        z = zipfile.ZipFile(io.BytesIO(blob))
        found = {n: z.read(n) for n in LEGACY_KEPT if n in z.namelist()}
    except zipfile.BadZipFile as e:
        raise RadError(f"legacy payload is not a zip: {e}") from e
    if len(found) != len(LEGACY_KEPT):
        raise RadError(f"legacy payload lacks {[n for n in LEGACY_KEPT if n not in found]}")
    return found


def _legacy_head(members: dict[str, bytes]) -> tuple[dict[str, Any], dict[str, Any]]:
    """The `statement_line` header columns of a legacy filing, and its `Documento` facts (form, reference date)."""
    doc = ET.fromstring(members["Documento.xml"])
    company = doc.find("CompanhiaAberta")
    form = _LEGACY_FORM.get(_text(doc, "CodigoTipoDocumento") or "")
    reference = _iso_day(_text(doc, "DataReferenciaDocumento"))
    scale = _SCALE.get(_text(doc, "CodigoEscalaMoeda") or "")
    currency = _CURRENCY.get(_text(doc, "CodigoMoeda") or "")
    if company is None or form is None or reference is None or scale is None or currency is None:
        raise RadError(
            f"legacy Documento: unknown type/reference/scale/currency {_text(doc, 'CodigoTipoDocumento')} "
            f"{_text(doc, 'CodigoEscalaMoeda')} {_text(doc, 'CodigoMoeda')}"
        )
    head: dict[str, Any] = {
        "form": form,
        "cnpj": _cnpj(_text(company, "NumeroCnpjCompanhiaAberta") or ""),
        "reference_date": reference,
        "version": int(_text(doc, "NumeroVersaoDocumento") or ""),
        "company_name": _text(company, "NomeRazaoSocialCompanhiaAberta"),
        "cd_cvm": (_text(company, "CodigoCvm") or "").zfill(6),
        "currency": currency,
        "scale": scale,
    }
    return head, {"reference": reference}


# The period ids that `ValorContaN` counts (period N of `PeriodoDemonstracaoFinanceira.xml`) are fixed by the system:
# a DFP has 1 (this fiscal year) and 2 (the last); an ITR has 2 (the quarter), 3 (the last fiscal year), 4 (year to
# date), 5 (the quarter a year earlier) and 6 (year to date a year earlier). The statements use: all of them in a
# DFP; in an ITR the balance sheet 2 and 3, the DRE and DRA 2, 4, 5 and 6, the DFC and DVA 4 and 6. A column is also
# used where the filing has a non-zero value (a period with only zeros is listed by open data, so it is a line here).
_LEGACY_PERIODS = {
    "dfp": dict.fromkeys(_LEGACY_STATEMENT.values(), (1, 2)),
    "itr": {
        **dict.fromkeys(("BPA", "BPP"), (2, 3)),
        **dict.fromkeys(("DRE", "DRA"), (2, 4, 5, 6)),
        **dict.fromkeys(("DFC_MD", "DFC_MI", "DVA"), (4, 6)),
    },
}


def _legacy_period_order(end: date, reference: date) -> str | None:
    """ÚLTIMO for the period that ends at the reference date, PENÚLTIMO for its counterpart a year earlier (or the end
    of the previous fiscal year, a balance sheet's); older periods (a third DMPL block) are not in open data."""
    if end == reference:
        return "ÚLTIMO"
    if end in (_year_before(reference), date(reference.year - 1, 12, 31)):
        return "PENÚLTIMO"
    return None


def parse_legacy(blob: bytes) -> tuple[pl.DataFrame, pl.DataFrame]:
    """A kept legacy payload (the stored zip of `extract_legacy`) as the open-data `statement_line` and
    `share_capital` contracts."""
    members = _legacy_members(blob)
    head, facts = _legacy_head(members)
    reference: date = facts["reference"]
    periods: dict[str, tuple[date | None, date]] = {}
    for _, e in ET.iterparse(io.BytesIO(members["PeriodoDemonstracaoFinanceira.xml"])):
        if e.tag == "PeriodoDemonstracaoFinanceira":
            end = _iso_day(_text(e, "DataFimPeriodo"))
            if end is not None:
                periods[_text(e, "NumeroIdentificacaoPeriodo") or ""] = (_iso_day(_text(e, "DataInicioPeriodo")), end)
            e.clear()
    records: list[dict[str, Any]] = []
    for _, e in ET.iterparse(io.BytesIO(members["InfoFinaDFin.xml"])):
        if e.tag != "InfoFinaDFin":
            continue
        plan = e.find("PlanoConta")
        version = None if plan is None else plan.find("VersaoPlanoConta")
        stmt = _LEGACY_STATEMENT.get(_text(version, "CodigoTipoDemonstracaoFinanceira") or "")
        cons = _LEGACY_CONSOLIDATION.get(_text(version, "CodigoTipoInformacaoFinanceira") or "")
        if stmt is None or cons is None or plan is None:
            raise RadError(
                f"legacy record {_text(e, 'NumeroIdentificadorInfoFinaDFin')}: unknown statement or consolidation"
            )
        records.append(
            {
                "id": _text(e, "NumeroIdentificadorInfoFinaDFin"),
                "statement": stmt,
                "consolidation": cons,
                "period": _text(e.find("PeriodoDemonstracaoFinanceira"), "NumeroIdentificacaoPeriodo") or "0",
                "code": _text(plan, "NumeroConta"),
                "fixed": _text(plan, "IndicadorContaFixa"),
                "name": None if e.find("DescricaoConta1") is None else e.findtext("DescricaoConta1"),
                "values": [_decimal(_text(e, f"ValorConta{n}")) for n in range(1, _LEGACY_VALUES + 1)],
            }
        )
        e.clear()
    # The columns a statement uses are the same for all its accounts and the zip does not list them: the template
    # above, plus any with a non-zero value; a DMPL (its records carry their period) has columns 1 to the last
    # non-zero one of any of its blocks, the labels being positional.
    seen: dict[tuple[str, str], set[int]] = {}
    for r in records:
        seen.setdefault((r["statement"], r["consolidation"]), set()).update(
            n for n, v in enumerate(r["values"], start=1) if v
        )
    rows: dict[tuple[Any, ...], dict[str, Any]] = {}
    for r in records:
        stmt, cons = r["statement"], r["consolidation"]
        dmpl = stmt == "DMPL"
        used = seen[(stmt, cons)] | set(_LEGACY_PERIODS[head["form"]].get(stmt, ()))
        for n, v in enumerate(r["values"], start=1):
            if v is None or not (n <= max(used, default=0) if dmpl else n in used):
                continue
            period_id = r["period"] if dmpl else str(n)
            if period_id not in periods:
                continue
            start, end = periods[period_id]
            order = _legacy_period_order(end, reference)
            if order is None:
                continue
            line = {
                **head,
                "statement": stmt,
                "consolidation": cons,
                "statement_group": ("DF Consolidado - " if cons == "con" else "DF Individual - ") + _GROUP_NAMES[stmt],
                "period_order": order,
                "period_start": None if stmt in ("BPA", "BPP") else start,
                "period_end": end,
                "equity_column": _legacy_label(n) if dmpl else None,
                "account_code": r["code"],
                "account_name": _clean_name(r["name"]),
                "value": v,
                "fixed_account": {"true": True, "false": False}.get(r["fixed"] or ""),
                "raw_locator": f"InfoFinaDFin.xml;id={r['id']};ValorConta{n}",
            }
            # a first-quarter ITR has the quarter and the year to date over the same dates: one line, as in open data
            key = (stmt, cons, order, line["period_start"], end, line["equity_column"], r["code"])
            kept = rows.get(key)
            if kept is None or kept["value"] == 0:
                rows[key] = line
            elif v != 0 and v != kept["value"]:
                raise RadError(
                    f"{stmt} {cons} {r['code']} {end}: two values for the same period, {kept['value']} and {v}"
                )
    df = pl.DataFrame(list(rows.values()), schema=SCHEMA) if rows else pl.DataFrame(schema=SCHEMA)
    return df, _legacy_capital(members, head)


def _decimal(text: str | None) -> Decimal | None:
    return None if text is None or not text.strip() else Decimal(text.strip())


def _legacy_label(n: int) -> str | None:
    return _LEGACY_EQUITY[n - 1] if n <= len(_LEGACY_EQUITY) else None


def _legacy_capital(members: dict[str, bytes], head: dict[str, Any]) -> pl.DataFrame:
    root = ET.fromstring(members["ComposicaoCapitalSocialDemonstracaoFinanceiraNegocios.xml"])
    comp = root.findall("ComposicaoCapitalSocialDemonstracaoFinanceira")
    if not comp:
        return pl.DataFrame(schema=CAPITAL_SCHEMA)
    if len(comp) != 1:
        raise RadError(f"{len(comp)} capital compositions")
    c = comp[0]
    out: dict[str, Any] = {k: head[k] for k in ("form", "cnpj", "reference_date", "version", "company_name")}
    names = {"common": "AcaoOrdinaria", "preferred": "AcaoPreferencial", "total": "TotalAcao"}
    for a, tag in (("paid_in", "CapitalIntegralizado"), ("treasury", "Tesouraria")):
        for b, el in names.items():
            v = _decimal(_text(c, f"Quantidade{el}{tag}"))
            out[f"{b}_{a}"] = int(v) if v is not None else (0 if a == "treasury" else None)
    return pl.DataFrame([out], schema=CAPITAL_SCHEMA)


def parse_payload(blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
    """One archived payload -> `statement_line` (and `share_capital`), partitioned like the open-data staging: a
    statements XML (PDFs stripped) or a kept legacy zip. The JSON record next to each payload (full sha256, members)
    and a legacy marker hold no data and parse to nothing."""
    prov = [pl.lit(row["raw_sha256"]).alias("raw_sha256"), pl.lit(row["ingest_run_id"]).alias("ingest_run_id")]
    if blob.startswith(b"PK"):
        df, cap = parse_legacy(blob)
        capital_locator = "legacy;path=ComposicaoCapitalSocialDemonstracaoFinanceiraNegocios.xml"
    elif blob.lstrip().startswith(b"<"):
        df, cap = parse_statements(blob), parse_capital(blob)
        capital_locator = "xml;path=Formulario/DadosEmpresa/ComposicaoCapital"
    else:
        raise NotData("RAD legacy layout (marker only): no statements to parse")
    for (form, year, stmt, cons), part in df.with_columns(year=pl.col("reference_date").dt.year()).group_by(
        "form", "year", "statement", "consolidation", maintain_order=True
    ):
        partition = f"form={form}/year={year}/statement={stmt}_{cons}"
        yield Parsed("statement_line", partition, part.drop("year").with_columns(*prov))
    if cap.height:
        c = cap.row(0, named=True)
        yield Parsed(
            "share_capital",
            f"form={c['form']}/year={c['reference_date'].year}",
            cap.with_columns(pl.lit(capital_locator).alias("raw_locator"), *prov),
        )


class CvmRadVersions(Connector):
    """The superseded versions of every DFP/ITR in the document index, from CVM's RAD (one zip each, ~10 MB, a
    request of its own: ADR-0027, ADR-0027 addendum for the legacy layout). Held versions are skipped, so the job
    resumes where it stopped."""

    source_id: ClassVar[str] = "cvm_rad_versions"
    version: ClassVar[str] = str(LEGACY_READER)
    contracts: ClassVar[dict[str, Contract]] = {"statement_line": STATEMENT_LINE, "share_capital": SHARE_CAPITAL}
    min_interval: ClassVar[float] = 0.25
    concurrency: ClassVar[int] = 12  # 16 parallel requests measured 2026-11-08: first byte 15-28 s, no errors (was 4)
    lookahead: ClassVar[int] = 6  # answers take 17-90 s: 72 queued keep the 12 workers busy
    cookies: ClassVar[bool] = False  # RAD's ASP.NET session serialises requests: 4 workers ran at the pace of 1
    timeout: ClassVar[float] = 600.0  # RAD builds each zip on request: some take minutes (3 timeouts at 120 s)
    dedup_staging: ClassVar[bool] = False

    def discover(self, mode: Mode, zones: Zones, **options: Any) -> Iterable[FetchSpec]:
        index = read_parquet_dir(zones.staging / "cvm_dfp_itr" / "document")
        if index is None:
            return
        fetched = (
            Manifest(zones.manifest)
            .read()
            .filter((pl.col("source_id") == self.source_id) & (pl.col("http_status") == 200))
            .select("notes", "raw_ext", "connector_version")
            .drop_nulls("notes")
        )
        # held: every stored version except a legacy marker of the connector before it read that layout
        stale = (pl.col("raw_ext") == "json") & (
            pl.col("connector_version").cast(pl.Int32, strict=False) < LEGACY_READER
        )
        held = {int(m.group(1)) for n in fetched.filter(~stale)["notes"] if (m := _DOC.search(n))}
        todo = (
            index.with_columns(latest=pl.col("version").max().over("form", "cnpj", "reference_date"))
            .filter(pl.col("version") < pl.col("latest"))
            .sort("reference_date", "doc_id", descending=True)
        )
        for r in todo.iter_rows(named=True):
            if r["doc_id"] in held:
                continue
            yield FetchSpec(
                self.source_id,
                "document",
                URL.format(doc_id=r["doc_id"]),
                "xml",
                reference_date=r["reference_date"],
                conditional=False,
                min_bytes=MIN_BYTES,
                extract=extract_statements,
                notes=f"doc={r['doc_id']};{r['form']};v{r['version']}",
            )

    def parse(self, blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
        return parse_payload(blob, row)
