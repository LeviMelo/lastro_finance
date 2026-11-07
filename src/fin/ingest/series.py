"""Economic and market series: source payloads -> staging `observation` + `definition` -> core `series_observation` and
`series_definition` (PLAN §4.3.4, one long table for every macro, rate and index series).

Staging is source-shaped: each observation keeps the date and the value **as the source wrote them**
(`period_text`, `value_text`); the definition keeps the source's own name, frequency and unit text. The core step
joins the two:
- the period comes from the definition's frequency: a monthly series stores `2024-03`, never a fake date;
- the unit is the source's unit text, on every row (PLAN §4.1 invariant 8); a series without a definition is
  quarantined, never published without a unit;
- **versions** (invariant 3): every archived payload is a snapshot of the series as published then. A value enters
  core when first seen and again only when a later payload changes it (`version` 1, 2…), with the first fetch that
  showed it as `kt_first_seen_at` and that payload as provenance.

Series ids are `<source_id>:<source code>`: `bcb_sgs:433`, `ipeadata:IGP12_IGPM12`,
`ibge_sidra:1737/v2266`, `ibge_sidra:7060/v63/c315/7169` (table, variable, class, category).
"""

from __future__ import annotations

import html
import json
import re
from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import polars as pl

from fin.config import Zones
from fin.ingest.base import NotData, Parsed
from fin.schema import Column, Contract, Rule
from fin.store.runs import IngestRun
from fin.store.tables import read_parquet_dir, write_parquet

VALUE = pl.Decimal(38, 24)  # measured 2026-11-07: up to 19 decimals (IGP index 1944) and 12 integer digits
KT = pl.Datetime("us", "UTC")
# Frequencies: D daily (a date), M month, Q quarter, A year, M3 rolling three months labelled by its last month.
FREQUENCIES = ("D", "M", "Q", "A", "M3")
# What the source writes where a value is not available, and its meaning (IBGE's conventions; '' is a JSON null).
# A parser may state another reason itself (`missing_reason`); any other text that is not a number is quarantined.
MISSING: dict[str, str] = {
    "...": "IBGE '...': not available",
    "..": "IBGE '..': not applicable",
    "X": "IBGE 'X': suppressed",
    "": "null in the source",
    "NA": "'NA': not available (NY Fed percentiles 2019-05-31, 2021-08-05)",
}


class LayoutError(ValueError):
    pass


OBSERVATION = Contract(
    table="staging.series.observation",
    version=2,
    description="One value of one series as one payload served it: date and value as written, and parsed.",
    columns=(
        Column("series_id", pl.String, "<source_id>:<source code>", "série", nullable=False),
        Column(
            "vt_date",
            pl.Date,
            "the date the source gives the value (period start for M/Q/A)",
            "data",
            "date",
            nullable=False,
        ),
        Column(
            "vt_until",
            pl.Date,
            "end date the source states (SGS `dataFim`, exclusive); null if none",
            "data fim",
            "date",
        ),
        Column(
            "period_text", pl.String, "the period as written by the source", "período como publicado", nullable=False
        ),
        Column(
            "value",
            VALUE,
            "the value, exact; null where the source marks it not available",
            "valor",
            "series_definition.unit",
        ),
        Column(
            "value_text", pl.String, "the value as written; '' for a JSON null", "valor como publicado", nullable=False
        ),
        Column(
            "missing_reason",
            pl.String,
            "why there is no value (the source's marker and its meaning); null when there is one",
            "motivo da ausência",
        ),
        Column(
            "kt_first_seen_at",
            KT,
            "when this payload was first fetched (UTC)",
            "visto pela primeira vez",
            "timestamp",
            nullable=False,
        ),
    ),
    rules=(
        Rule("value_or_missing_reason", pl.col("value").is_not_null() ^ pl.col("missing_reason").is_not_null()),
        Rule("until_after_date", pl.col("vt_until").is_null() | (pl.col("vt_until") > pl.col("vt_date"))),
    ),
    key=("series_id", "vt_date", "raw_sha256"),
)

DEFINITION = Contract(
    table="staging.series.definition",
    version=1,
    description="A series' name, frequency and unit as its source describes it, from one metadata payload.",
    columns=(
        Column("series_id", pl.String, "<source_id>:<source code>", "série", nullable=False),
        Column("source_code", pl.String, "the source's own code", "código na fonte", nullable=False),
        Column("name", pl.String, "the source's name for the series (pt-BR as published)", "nome", nullable=False),
        Column("frequency", pl.String, "D, M, Q, A or M3 (rolling 3 months)", "periodicidade", nullable=False),
        Column(
            "frequency_text", pl.String, "frequency as written by the source", "periodicidade na fonte", nullable=False
        ),
        Column("unit", pl.String, "unit as written by the source, with its multiplier", "unidade", nullable=False),
        Column(
            "kt_first_seen_at",
            KT,
            "when this payload was first fetched (UTC)",
            "visto pela primeira vez",
            "timestamp",
            nullable=False,
        ),
    ),
    rules=(Rule("frequency_known", pl.col("frequency").is_in(FREQUENCIES)),),
    key=("series_id", "raw_sha256"),
)

SERIES_OBSERVATION = Contract(
    table="core.series_observation",
    version=1,
    description="Every value of every series, versioned: one row per (series, period, value as first seen).",
    columns=(
        Column("series_id", pl.String, "<source_id>:<source code>", "série", nullable=False),
        Column(
            "vt_reference",
            pl.String,
            "period: 2024-03-15 (D), 2024-03-15..2024-04-14 (D with a stated end), 2024-03 (M), 2024Q1, 2024, "
            "2024-01..2024-03 (M3)",
            "período de referência",
            nullable=False,
        ),
        Column("vt_start", pl.Date, "first day of the period", "início do período", "date", nullable=False),
        Column("vt_end", pl.Date, "last day of the period (inclusive)", "fim do período", "date", nullable=False),
        Column("frequency", pl.String, "D, M, Q, A or M3", "periodicidade", nullable=False),
        Column("value", VALUE, "the value, exact", "valor", "column `unit`", nullable=False),
        Column("unit", pl.String, "unit as written by the source", "unidade", nullable=False),
        Column(
            "version",
            pl.Int32,
            "1 for the first value seen; +1 at each change in a later payload",
            "versão",
            "count",
            nullable=False,
        ),
        Column(
            "kt_first_seen_at",
            KT,
            "first fetch of a payload showing this value",
            "conhecido desde",
            "timestamp",
            nullable=False,
        ),
        Column("kt_published_at", KT, "publication time, where the source states it", "publicado em", "timestamp"),
    ),
    rules=(
        Rule("frequency_known", pl.col("frequency").is_in(FREQUENCIES)),
        Rule("period_aligned", pl.col("vt_start") <= pl.col("vt_end")),
    ),
    key=("series_id", "vt_reference", "version"),
)

SERIES_DEFINITION = Contract(
    table="core.series_definition",
    version=1,
    description="The latest definition of each series, from the most recent metadata payload.",
    columns=DEFINITION.columns,
    key=("series_id",),
)


# ------------------------------------------------------------------------------------------------ helpers


def _decimal(texts: pl.Expr) -> pl.Expr:
    return texts.str.strip_chars().cast(VALUE, strict=False)


def _frame(rows: list[dict[str, Any]], row: dict[str, Any], schema: dict[str, Any]) -> pl.DataFrame:
    df = pl.DataFrame(rows, schema=schema, orient="row")
    return df.with_columns(
        pl.lit(row["fetched_at"], dtype=KT).alias("kt_first_seen_at"),
        pl.lit(row["raw_sha256"]).alias("raw_sha256"),
        pl.lit(row["ingest_run_id"]).alias("ingest_run_id"),
    )


_OBS_IN = {
    "series_id": pl.String,
    "vt_date": pl.Date,
    "vt_until": pl.Date,
    "period_text": pl.String,
    "value_text": pl.String,
    "value_norm": pl.String,  # the number to read when value_text is formatted (pt-BR text in a spreadsheet)
    "missing_reason": pl.String,
    "raw_locator": pl.String,
}
_DEF_IN = {
    "series_id": pl.String,
    "source_code": pl.String,
    "name": pl.String,
    "frequency": pl.String,
    "frequency_text": pl.String,
    "unit": pl.String,
    "raw_locator": pl.String,
}


def _plain(text: str | None) -> str | None:
    """Exponent notation (Ipeadata: `3.08619E-05`) written out exactly; None when the text needs no change.
    A number with more decimals than VALUE holds is refused: the cast would round it silently."""
    if text is None:
        return None
    norm = text
    if "e" in text.lower():
        try:
            norm = format(Decimal(text), "f")
        except InvalidOperation:
            return None  # not a number: the contract quarantines it
    if len(norm.partition(".")[2]) > VALUE.scale:
        raise LayoutError(f"value {text!r} has more than {VALUE.scale} decimals")
    return norm if norm != text else None


def _observations(rows: list[dict[str, Any]], row: dict[str, Any]) -> pl.DataFrame:
    rows = [r | {"value_norm": r.get("value_norm") or _plain(r.get("value_text"))} for r in rows]
    df = _frame([{k: r.get(k) for k in _OBS_IN} for r in rows], row, _OBS_IN)
    reason = pl.coalesce(
        pl.col("missing_reason"), pl.col("value_text").replace_strict(MISSING, default=None, return_dtype=pl.String)
    )
    number = _decimal(pl.coalesce(pl.col("value_norm"), pl.col("value_text")))
    return df.with_columns(reason.alias("missing_reason"), pl.when(reason.is_null()).then(number).alias("value")).drop(
        "value_norm"
    )


def _dmy(text: str) -> date:
    d, m, y = text.split("/")
    return date(int(y), int(m), int(d))


def _url(row: dict[str, Any]) -> str:
    return str(json.loads(row["request"])["url"])


# ------------------------------------------------------------------------------------------------ BCB SGS


def parse_sgs(blob: bytes, row: dict[str, Any], code: str) -> pl.DataFrame:
    """`[{"data":"dd/mm/aaaa","valor":"0.05"[,"dataFim":"dd/mm/aaaa"]}]` (docs/sources/bcb_sgs.md §3)."""
    if blob.lstrip()[:1] == b"<" and b"Requisi" in blob:
        # BCB's gateway answers some requests with an HTML "Requisição inválida!" page and HTTP 200 (seen 2026-11-07)
        raise NotData(f"SGS {code}: BCB 'Requisição inválida' page served with HTTP 200")
    items = json.loads(blob)
    if not isinstance(items, list):
        raise LayoutError(f"SGS {code}: expected a JSON array, got {type(items).__name__}")
    rows: list[dict[str, Any]] = []
    for i, it in enumerate(items):
        until = it.get("dataFim")
        rows.append(
            {
                "series_id": f"bcb_sgs:{code}",
                "vt_date": _dmy(it["data"]),
                "vt_until": _dmy(until) if until else None,
                "period_text": it["data"] + (f"..{until}" if until else ""),
                "value_text": "" if it["valor"] is None else str(it["valor"]),
                "raw_locator": f"$[{i}]",
            }
        )
    return _observations(rows, row)


_SGS_FREQ = {"D": "D", "M": "M", "T": "Q", "A": "A"}


def parse_sgs_meta(blob: bytes, row: dict[str, Any]) -> pl.DataFrame:
    """SGS SOAP `getUltimoValorXML`: <NOME>, <CODIGO>, <PERIODICIDADE> (D/M/T/A), <UNIDADE>; the payload is an
    XML document escaped inside the SOAP envelope (measured 2026-11-07)."""
    text = html.unescape(blob.decode("utf-8"))

    def tag(name: str) -> str:
        m = re.search(f"<{name}>(.*?)</{name}>", text, re.S)
        if not m:
            raise LayoutError(f"SGS metadata: no <{name}> in the response")
        return m.group(1).strip()

    code, freq = tag("CODIGO"), tag("PERIODICIDADE")
    rows = [
        {
            "series_id": f"bcb_sgs:{code}",
            "source_code": code,
            "name": tag("NOME"),
            "frequency": _SGS_FREQ.get(freq, f"?{freq}"),
            "frequency_text": freq,
            "unit": tag("UNIDADE"),
            "raw_locator": "SERIE",
        }
    ]
    return _frame(rows, row, _DEF_IN)


def sgs_meta_envelope(code: int | str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?><soapenv:Envelope '
        'xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
        'xmlns:pub="http://publico.ws.casosdeuso.sgs.pec.bcb.gov.br"><soapenv:Body><pub:getUltimoValorXML>'
        f"<in0>{code}</in0></pub:getUltimoValorXML></soapenv:Body></soapenv:Envelope>"
    )


def parse_sgs_payload(blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
    ds = str(row["dataset_id"])
    if ds == "sgs_meta":
        df = parse_sgs_meta(blob, row)
        yield Parsed("definition", f"code={df['source_code'][0]}", df)
    elif ds.startswith("sgs_"):
        yield Parsed("observation", ds, parse_sgs(blob, row, ds.removeprefix("sgs_")))


# ------------------------------------------------------------------------------------------------ Ipeadata

_IPEA_FREQ = {"Diária": "D", "Mensal": "M", "Trimestral": "Q", "Anual": "A"}


def parse_ipeadata(blob: bytes, row: dict[str, Any]) -> pl.DataFrame:
    """OData `ValoresSerie`: {"value":[{"SERCODIGO","VALDATA":"1994-04-29T00:00:00-03:00","VALVALOR":1120.0}]}.
    Numbers are JSON doubles: each is read as the shortest decimal that round-trips to it (docs/sources/ipeadata.md)."""
    doc = json.loads(blob, parse_float=str, parse_int=str)
    rows: list[dict[str, Any]] = []
    for i, it in enumerate(doc["value"]):
        if it.get("NIVNOME") or it.get("TERCODIGO"):
            raise LayoutError(f"Ipeadata {it['SERCODIGO']}: regional rows (NIVNOME/TERCODIGO) are not parsed")
        v = it["VALVALOR"]
        rows.append(
            {
                "series_id": f"ipeadata:{it['SERCODIGO']}",
                "vt_date": date.fromisoformat(it["VALDATA"][:10]),
                "vt_until": None,
                "period_text": it["VALDATA"],
                "value_text": "" if v is None else str(v),
                # a JSON double printed to 17 digits (4.1469769999999997E-13): its value is the shortest decimal
                # that round-trips to the same double (4.146977E-13), as for spreadsheet cells
                "value_norm": None if v is None else format(Decimal(repr(float(v))), "f"),
                "raw_locator": f"$.value[{i}]",
            }
        )
    return _observations(rows, row)


def parse_ipeadata_meta(blob: bytes, row: dict[str, Any]) -> pl.DataFrame:
    """OData `Metadados('<code>')`: SERNOME, PERNOME (Diária/Mensal/…), UNINOME and MULNOME (multiplier)."""
    rows: list[dict[str, Any]] = []
    for i, it in enumerate(json.loads(blob)["value"]):
        unit = str(it.get("UNINOME") or "")
        if it.get("MULNOME"):
            unit = f"{unit} ({it['MULNOME']})"
        per = str(it.get("PERNOME") or "")
        rows.append(
            {
                "series_id": f"ipeadata:{it['SERCODIGO']}",
                "source_code": it["SERCODIGO"],
                "name": it["SERNOME"],
                "frequency": _IPEA_FREQ.get(per, f"?{per}"),
                "frequency_text": per,
                "unit": unit,
                "raw_locator": f"$.value[{i}]",
            }
        )
    return _frame(rows, row, _DEF_IN)


def parse_ipeadata_payload(blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
    ds = str(row["dataset_id"])
    if ds.startswith("meta_"):
        yield Parsed("definition", ds, parse_ipeadata_meta(blob, row))
    else:
        yield Parsed("observation", ds, parse_ipeadata(blob, row))


# ------------------------------------------------------------------------------------------------ IBGE SIDRA

_SIDRA_PERIOD = {"Mês": "M", "Trimestre": "Q", "Trimestre Móvel": "M3", "Ano": "A"}


def _sidra_date(code: str, freq: str) -> date:
    y = int(code[:4])
    if freq == "A":
        return date(y, 1, 1)
    n = int(code[4:6])
    if freq == "Q":
        if not 1 <= n <= 4:
            raise LayoutError(f"SIDRA quarter code {code}")
        return date(y, 3 * n - 2, 1)
    return date(y, n, 1)  # M, and M3 labelled by its last month


def parse_sidra(blob: bytes, row: dict[str, Any]) -> tuple[pl.DataFrame, pl.DataFrame]:
    """SIDRA `/values`: a header object naming the dimensions, then one object per value with `V` (value text), `MN`
    (unit), `D2C`/`D2N` (variable), `D3C`/`D3N` (period) and optionally `D4C`/`D4N` (one class category). The class
    code is read from the request path (`/c315/`)."""
    items = json.loads(blob)
    header, body = items[0], items[1:]
    if header.get("D2N") != "Variável" or "D3N" not in header:
        raise LayoutError(f"SIDRA: unexpected header {header}")
    if "D5N" in header:
        raise LayoutError("SIDRA: more than one class dimension is not parsed")
    freq = _SIDRA_PERIOD.get(header["D3N"])
    if freq is None:
        raise LayoutError(f"SIDRA: period dimension {header['D3N']!r} unknown")
    path = _url(row).split("/values/", 1)[1]
    table = re.search(r"(?:^|/)t/(\d+)", path)
    cls = re.search(r"/c(\d+)/", path + "/")
    if table is None:
        raise LayoutError(f"SIDRA: no table in {path}")
    has_class = "D4N" in header
    if has_class and cls is None:
        raise LayoutError(f"SIDRA: class dimension without /c<code>/ in {path}")
    obs: list[dict[str, Any]] = []
    defs: dict[str, dict[str, Any]] = {}
    for i, it in enumerate(body, start=1):
        code = f"{table.group(1)}/v{it['D2C']}" + (f"/c{cls.group(1)}/{it['D4C']}" if has_class and cls else "")
        sid = f"ibge_sidra:{code}"
        obs.append(
            {
                "series_id": sid,
                "vt_date": _sidra_date(it["D3C"], freq),
                "vt_until": None,
                "period_text": f"{it['D3C']} ({it['D3N']})",
                "value_text": it["V"],
                "raw_locator": f"$[{i}]",
            }
        )
        if it["MN"] and sid not in defs:  # rows of a missing value carry an empty unit
            name = it["D2N"] + (f" — {it['D4N']}" if has_class else "")
            defs[sid] = {
                "series_id": sid,
                "source_code": code,
                "name": name,
                "frequency": freq,
                "frequency_text": header["D3N"],
                "unit": it["MN"],
                "raw_locator": f"$[{i}]",
            }
    return _observations(obs, row), _frame(list(defs.values()), row, _DEF_IN)


def parse_sidra_payload(blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
    obs, defs = parse_sidra(blob, row)
    yield Parsed("observation", str(row["dataset_id"]), obs)
    yield Parsed("definition", str(row["dataset_id"]), defs)


# ------------------------------------------------------------------------------------------------ Tesouro VNA

VNA_UNIT = "BRL per bond (VNA, valor nominal atualizado)"  # docs/sources/tesouro_vna.md


def _xlsx_number(v: object) -> tuple[str, str | None]:
    """(value as written, number to read). openpyxl returns the cell's float; its shortest repr is the published
    decimal (the XML holds e.g. 1051.9850879999999 for 1051.985088). A text cell is pt-BR (' 3.580,282456')."""
    if isinstance(v, bool) or v is None:
        return ("" if v is None else str(v)), None
    if isinstance(v, int | float):
        return repr(v), None
    text = str(v)
    return text, text.replace("\xa0", "").strip().replace(".", "").replace(",", ".")


def parse_tesouro_vna(blob: bytes, row: dict[str, Any]) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Tesouro's VNA workbooks (publicacao/53360 NTN-B, 45833 NTN-C): a header row starting `DATA`, then one row
    per month: date, then one VNA per column (NTN-C: one column per group of maturities). A zero VNA after a
    group's last maturity means no VNA, not a value of zero."""
    import io

    import openpyxl

    ws = openpyxl.load_workbook(io.BytesIO(blob), data_only=True, read_only=True).worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    hdr = next((i for i, r in enumerate(rows) if r and r[0] == "DATA"), None)
    if hdr is None:
        raise LayoutError("VNA workbook: no header row starting with DATA")
    head = [c for c in rows[hdr][1:] if c is not None]
    if len(head) == 1:  # NTN-B: the title sits in the header row itself
        names = {1: ("NTN-B", str(head[0]))}
    else:
        names = {}
        for j, c in enumerate(rows[hdr][1:], start=1):
            if c is None:
                continue
            years = re.findall(r"(?:19|20)\d\d", str(c))
            if not years:
                raise LayoutError(f"VNA workbook: column header without maturities: {c!r}")
            names[j] = ("NTN-C/" + "+".join(years), f"VALORES NOMINAIS DE NTN-C — {c}")
    obs: list[dict[str, Any]] = []
    for i, r in enumerate(rows[hdr + 1 :], start=hdr + 2):
        if not r or r[0] is None:
            continue
        if not isinstance(r[0], datetime):
            raise LayoutError(f"VNA workbook row {i}: date cell {r[0]!r}")
        for j, (code, _) in names.items():
            text, norm = _xlsx_number(r[j] if j < len(r) else None)
            zero = text in ("0", "0.0")
            obs.append(
                {
                    "series_id": f"tesouro_vna:{code}",
                    "vt_date": r[0].date(),
                    "vt_until": None,
                    "period_text": r[0].date().isoformat(),
                    "value_text": text,
                    "value_norm": norm,
                    "missing_reason": "VNA 0: the group's bonds have matured" if zero else None,
                    "raw_locator": f"{ws.title}!R{i}C{j + 1}",
                }
            )
    defs = [
        {
            "series_id": f"tesouro_vna:{code}",
            "source_code": code,
            "name": name,
            "frequency": "D",
            "frequency_text": "monthly, dated on the VNA's reference day",
            "unit": VNA_UNIT,
            "raw_locator": f"{ws.title}!R{hdr + 1}",
        }
        for code, name in names.values()
    ]
    return _observations(obs, row), _frame(defs, row, _DEF_IN)


def parse_tesouro_vna_payload(blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
    obs, defs = parse_tesouro_vna(blob, row)
    yield Parsed("observation", str(row["dataset_id"]), obs)
    yield Parsed("definition", str(row["dataset_id"]), defs)


# ------------------------------------------------------------------------------------------------ wide CSVs
# Treasury, NY Fed and Cboe publish one row per date and one column per series. An empty cell is a series not
# published that day (a tenor added later, a field before it existed): it is absent, not a missing value, so it
# yields no row. Units are not in these payloads; each is declared here from the source note it cites.


def _wide(
    blob: bytes,
    row: dict[str, Any],
    date_col: str,
    columns: dict[str, tuple[str, str, str]],
    *,
    fixed: dict[str, str] | None = None,
    flags: tuple[str, ...] = (),
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """`columns`: header -> (series_id, name, unit). A header of the payload in neither `columns` nor `fixed` is a
    layout change and raises. `fixed`: header -> the only value it may hold (e.g. NY Fed `Rate Type`)."""
    import io

    df = pl.read_csv(io.BytesIO(blob), infer_schema=False)
    known = {date_col, *columns, *(fixed or {}), *flags}
    extra = [c for c in df.columns if c not in known]
    if extra or date_col not in df.columns:
        raise LayoutError(f"wide CSV: unknown columns {extra} (date column {date_col!r})")
    for col, want in (fixed or {}).items():
        got = set(df[col].drop_nulls().unique().to_list()) if col in df.columns else set()
        if got - {want}:
            raise LayoutError(f"wide CSV: {col} holds {sorted(got)}, expected {want!r}")
    obs: list[dict[str, Any]] = []
    for i, r in enumerate(df.iter_rows(named=True), start=2):
        if all(v is None for v in r.values()):
            continue  # a blank line (NY Fed ends its CSV with one)
        m, d, y = r[date_col].split("/")
        day = date(int(y), int(m), int(d))
        for col, (sid, _, _) in columns.items():
            v = r.get(col)
            if v is None or not v.strip():
                continue
            obs.append(
                {
                    "series_id": sid,
                    "vt_date": day,
                    "vt_until": None,
                    "period_text": r[date_col],
                    "value_text": v,
                    "raw_locator": f"line={i};column={col}",
                }
            )
    defs = [
        {
            "series_id": columns[c][0],
            "source_code": c,
            "name": columns[c][1],
            "frequency": "D",
            "frequency_text": "daily (one row per published date)",
            "unit": columns[c][2],
            "raw_locator": f"header:{c}",
        }
        for c in columns
        if c in df.columns
    ]
    return _observations(obs, row), _frame(defs, row, _DEF_IN)


def _tenor(header: str) -> str:
    """'1 Mo' -> 1M, '1.5 Month' -> 1.5M, '10 Yr' / '10 YR' -> 10Y."""
    n, unit = header.split(" ", 1)
    return n + ("M" if unit.lower().startswith("mo") else "Y")


TREASURY_CURVES = {  # docs/sources/context_global.md section 1
    "daily_treasury_yield_curve": ("par", "US Treasury par yield curve rate", "% p.a. (bond-equivalent)"),
    "daily_treasury_real_yield_curve": ("real", "US Treasury real (TIPS) par yield curve rate", "% p.a. real"),
}
TREASURY_TENORS = (
    "1 Mo", "1.5 Month", "2 Mo", "3 Mo", "4 Mo", "6 Mo", "1 Yr", "2 Yr", "3 Yr", "5 Yr", "7 Yr", "10 Yr", "20 Yr",
    "30 Yr", "5 YR", "7 YR", "10 YR", "20 YR", "30 YR",
)  # fmt: skip


def parse_us_treasury(blob: bytes, row: dict[str, Any]) -> tuple[pl.DataFrame, pl.DataFrame]:
    key, name, unit = TREASURY_CURVES[str(row["dataset_id"])]
    cols = {h: (f"us_treasury:{key}/{_tenor(h)}", f"{name}, {h}", unit) for h in TREASURY_TENORS}
    return _wide(blob, row, "Date", cols)


NYFED_FIELDS = {  # header -> (field, unit); units as the headers state them (docs/sources/context_global.md)
    "Rate (%)": ("rate", "% p.a."),
    "1st Percentile (%)": ("p01", "% p.a."),
    "25th Percentile (%)": ("p25", "% p.a."),
    "75th Percentile (%)": ("p75", "% p.a."),
    "99th Percentile (%)": ("p99", "% p.a."),
    "Volume ($Billions)": ("volume", "USD billions"),
    "Target Rate From (%)": ("target_from", "% p.a."),
    "Target Rate To (%)": ("target_to", "% p.a."),
    "Intra Day - Low (%)": ("intraday_low", "% p.a."),
    "Intra Day - High (%)": ("intraday_high", "% p.a."),
    "Standard Deviation (%)": ("std", "% p.a."),
    "30-Day Average SOFR": ("avg30", "% p.a."),
    "90-Day Average SOFR": ("avg90", "% p.a."),
    "180-Day Average SOFR": ("avg180", "% p.a."),
    "SOFR Index": ("index", "index"),
}
NYFED_RATES = {"unsecured_effr": "EFFR", "secured_sofr": "SOFR"}


def parse_nyfed(blob: bytes, row: dict[str, Any]) -> tuple[pl.DataFrame, pl.DataFrame]:
    """NY Fed `search.csv`: one row per date. `Revision Indicator (Y/N)` ('r') and `Footnote ID` are flags, not
    series: they stay in raw."""
    rate = NYFED_RATES[str(row["dataset_id"])]
    cols = {h: (f"nyfed:{rate}/{f}", f"{rate} {h}", u) for h, (f, u) in NYFED_FIELDS.items()}
    flags = ("Revision Indicator (Y/N)", "Footnote ID")
    return _wide(blob, row, "Effective Date", cols, fixed={"Rate Type": rate}, flags=flags)


def parse_cboe(blob: bytes, row: dict[str, Any]) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Cboe `<INDEX>_History.csv`: DATE + OPEN/HIGH/LOW/CLOSE, or DATE + one column named after the index."""
    idx = str(row["dataset_id"]).upper()
    unit = "index points"  # docs/sources/context_global.md section 3
    cols = {f: (f"cboe:{idx}/{f}", f"Cboe {idx} {f.lower()}", unit) for f in ("OPEN", "HIGH", "LOW", "CLOSE")}
    cols[idx] = (f"cboe:{idx}/CLOSE", f"Cboe {idx} close", unit)
    return _wide(blob, row, "DATE", cols)


# ------------------------------------------------------------------------------------------------ SDMX
# ECB, BIS and OECD serve SDMX-CSV: one row per observation, dimensions and attributes as columns. The unit is a code
# (ECB UNIT, BIS/OECD UNIT_MEASURE); its label comes from the source's own codelist, archived monthly and joined in
# core (`unit_label`), so no label is typed by hand.

SDMX_FREQ = {"D": "D", "B": "D", "M": "M", "Q": "Q", "A": "A"}
SDMX_KEYS: dict[str, tuple[str, ...]] = {  # flow -> its dimensions, in key order (measured on the payload headers)
    "BIS:WS_CBPOL": ("FREQ", "REF_AREA"),
    "BIS:WS_EER": ("FREQ", "EER_TYPE", "EER_BASKET", "REF_AREA"),
    "OECD:DF_CLI": (
        "REF_AREA", "FREQ", "MEASURE", "UNIT_MEASURE", "ACTIVITY", "ADJUSTMENT", "TRANSFORMATION", "TIME_HORIZ",
        "METHODOLOGY",
    ),
}  # fmt: skip

UNIT_LABEL = Contract(
    table="staging.series.unit_label",
    version=1,
    description="A unit code and its label, from a source's own SDMX codelist.",
    columns=(
        Column(
            "codelist",
            pl.String,
            "codelist id (CL_UNIT, CL_BIS_UNIT, CL_UNIT_MEASURE)",
            "lista de códigos",
            nullable=False,
        ),
        Column("code", pl.String, "unit code as the data files write it", "código", nullable=False),
        Column("label", pl.String, "English label", "rótulo", nullable=False),
        Column(
            "kt_first_seen_at",
            KT,
            "when this payload was first fetched (UTC)",
            "visto pela primeira vez",
            "timestamp",
            nullable=False,
        ),
    ),
    key=("codelist", "code", "raw_sha256"),
)


def _sdmx_date(period: str, freq: str) -> date:
    if freq == "D":
        return date.fromisoformat(period)
    if freq == "M":
        return date.fromisoformat(period + "-01")
    if freq == "Q":
        y, q = period.split("-Q")
        return date(int(y), 3 * int(q) - 2, 1)
    if freq == "A":
        return date(int(period), 1, 1)
    raise LayoutError(f"SDMX period {period!r} of frequency {freq}")


def parse_sdmx_csv(blob: bytes, row: dict[str, Any], source: str) -> tuple[pl.DataFrame, pl.DataFrame]:
    import io

    df = pl.read_csv(io.BytesIO(blob), infer_schema=False)
    for need in ("FREQ", "TIME_PERIOD", "OBS_VALUE"):
        if need not in df.columns:
            raise LayoutError(f"SDMX-CSV ({source}): no {need} column")
    if "KEY" in df.columns:  # ECB writes the series key itself
        key = pl.col("KEY")
    else:
        flow = re.search(r"(DF_[A-Z_]+|WS_[A-Z_]+)", _url(row))
        dims = SDMX_KEYS.get(f"{source.upper()}:{flow.group(1)}" if flow else "")
        if dims is None or any(d not in df.columns for d in dims):
            raise LayoutError(f"SDMX-CSV ({source}): no known dimensions for {_url(row)}")
        key = pl.lit(f"{flow.group(1)}.") + pl.concat_str([pl.col(d) for d in dims], separator=".")  # type: ignore[union-attr]
    unit_col = "UNIT" if "UNIT" in df.columns else "UNIT_MEASURE"
    if unit_col not in df.columns:
        raise LayoutError(f"SDMX-CSV ({source}): no unit column")
    title = next((c for c in ("TITLE", "TITLE_TS") if c in df.columns), None)
    mult = pl.col("UNIT_MULT") if "UNIT_MULT" in df.columns else pl.lit("0")
    frame = df.with_row_index("i", offset=2).select(
        (pl.lit(f"{source}:") + key).alias("series_id"),
        key.alias("source_code"),
        pl.col("FREQ").alias("freq"),
        pl.col("TIME_PERIOD").alias("period"),
        pl.col("OBS_VALUE").fill_null("").alias("value_text"),
        pl.when(mult.fill_null("0") == "0")
        .then(pl.col(unit_col))
        .otherwise(pl.col(unit_col) + " x10^" + mult)
        .alias("unit"),
        (pl.col(title).str.strip_chars() if title else key).alias("name"),
        pl.col("i"),
    )
    bad_freq = set(frame["freq"].unique().to_list()) - set(SDMX_FREQ)
    if bad_freq:
        raise LayoutError(f"SDMX-CSV ({source}): frequencies {sorted(bad_freq)}")
    obs = [
        {
            "series_id": r["series_id"],
            "vt_date": _sdmx_date(r["period"], SDMX_FREQ[r["freq"]]),
            "vt_until": None,
            "period_text": r["period"],
            "value_text": r["value_text"],
            "raw_locator": f"line={r['i']}",
        }
        for r in frame.iter_rows(named=True)
    ]
    first = frame.unique("series_id", keep="first", maintain_order=True)
    defs = [
        {
            "series_id": r["series_id"],
            "source_code": r["source_code"],
            "name": r["name"],
            "frequency": SDMX_FREQ[r["freq"]],
            "frequency_text": r["freq"],
            "unit": r["unit"],
            "raw_locator": f"line={r['i']}",
        }
        for r in first.iter_rows(named=True)
    ]
    return _observations(obs, row), _frame(defs, row, _DEF_IN)


def parse_sdmx_codelist(blob: bytes, row: dict[str, Any], want: str) -> pl.DataFrame:
    """Codes and English labels of the codelists whose id contains `want`: an SDMX 2.1 structure message (XML) or
    SDMX-JSON (BIS)."""
    out: list[dict[str, Any]] = []
    if blob.lstrip()[:1] == b"{":
        doc = json.loads(blob)
        for cl in doc["data"]["codelists"]:
            if want in cl["id"]:
                out += [
                    {"codelist": cl["id"], "code": c["id"], "label": c.get("name") or c["names"]["en"]}
                    for c in cl["codes"]
                ]
    else:
        import xml.etree.ElementTree as ET

        root = ET.fromstring(blob)
        for cl in root.iter():
            if not cl.tag.endswith("}Codelist") or want not in cl.get("id", ""):
                continue
            for c in cl:
                if not c.tag.endswith("}Code"):
                    continue
                names = [n for n in c if n.tag.endswith("}Name")]
                en = next((n.text for n in names if n.get("{http://www.w3.org/XML/1998/namespace}lang") == "en"), None)
                out.append(
                    {"codelist": cl.get("id"), "code": c.get("id"), "label": en or (names[0].text if names else "")}
                )
    if not out:
        raise LayoutError(f"no codelist matching {want!r} in the structure payload")
    df = pl.DataFrame(out, schema={"codelist": pl.String, "code": pl.String, "label": pl.String}, orient="row")
    return df.with_columns(
        pl.lit(row["fetched_at"], dtype=KT).alias("kt_first_seen_at"),
        pl.lit(row["raw_sha256"]).alias("raw_sha256"),
        (pl.lit("codelist=") + pl.col("codelist") + ";code=" + pl.col("code")).alias("raw_locator"),
        pl.lit(row["ingest_run_id"]).alias("ingest_run_id"),
    )


SDMX_CODELISTS = {"ecb": "CL_UNIT", "bis": "CL_BIS_UNIT", "oecd": "CL_UNIT_MEASURE"}


def _sdmx(source: str) -> Any:
    def payload(blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
        ds = str(row["dataset_id"])
        if ds.startswith(("codelist_", "dsd_")):
            yield Parsed("unit_label", ds, parse_sdmx_codelist(blob, row, SDMX_CODELISTS[source]))
            return
        obs, defs = parse_sdmx_csv(blob, row, source)
        yield Parsed("observation", ds, obs)
        yield Parsed("definition", ds, defs)

    return payload


# ------------------------------------------------------------------------------------------------ World Bank
# Pink Sheet `CMO-Historical-Data-Monthly.xlsx`, sheet "Monthly Prices": a title block, a row of commodity names,
# a row of units (`($/bbl)`), then one row per month (`1960M01`); `…` marks a month without a price. The index sheet
# (hierarchical headers, 2010=100) is not parsed yet.

WB_MISSING = {m: f"World Bank '{m}': not available" for m in ("…", "...", "..")}


def _slug_code(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower().replace("*", "")).strip("_")


def parse_worldbank_cmo(blob: bytes, row: dict[str, Any]) -> tuple[pl.DataFrame, pl.DataFrame]:
    import io

    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(blob), data_only=True, read_only=True)
    if "Monthly Prices" not in wb.sheetnames:
        raise LayoutError(f"Pink Sheet: no 'Monthly Prices' sheet in {wb.sheetnames}")
    ws = wb["Monthly Prices"]
    rows = list(ws.iter_rows(values_only=True))
    first = next(
        (i for i, r in enumerate(rows) if r and isinstance(r[0], str) and re.fullmatch(r"\d{4}M\d\d", r[0])), None
    )
    if first is None or first < 2:
        raise LayoutError("Pink Sheet: no monthly rows (YYYYMmm)")
    names, units = rows[first - 2], rows[first - 1]
    cols: dict[int, tuple[str, str, str]] = {}
    for j in range(1, len(names)):
        name = names[j]
        if name is None:
            continue
        unit = units[j] if j < len(units) else None
        if not (isinstance(unit, str) and unit.startswith("(")):
            raise LayoutError(f"Pink Sheet: column {name!r} has no unit cell ({unit!r})")
        cols[j] = (f"worldbank_cmo:{_slug_code(str(name))}", str(name).strip(), unit.strip("()"))
    if len({c[0] for c in cols.values()}) != len(cols):
        raise LayoutError("Pink Sheet: two commodity columns share a name")
    obs: list[dict[str, Any]] = []
    for i, r in enumerate(rows[first:], start=first + 1):
        if not r or r[0] is None:
            continue
        if not (isinstance(r[0], str) and re.fullmatch(r"\d{4}M\d\d", r[0])):
            raise LayoutError(f"Pink Sheet row {i}: period {r[0]!r}")
        y, mo = r[0].split("M")
        for j, (sid, _, _) in cols.items():
            v = r[j] if j < len(r) else None
            text, norm = _xlsx_number(v)
            obs.append(
                {
                    "series_id": sid,
                    "vt_date": date(int(y), int(mo), 1),
                    "vt_until": None,
                    "period_text": r[0],
                    "value_text": text,
                    "value_norm": norm if v is None or isinstance(v, int | float) else None,
                    "missing_reason": WB_MISSING.get(text),
                    "raw_locator": f"Monthly Prices!R{i}C{j + 1}",
                }
            )
    defs = [
        {
            "series_id": sid,
            "source_code": name,
            "name": name,
            "frequency": "M",
            "frequency_text": "monthly (YYYYMmm)",
            "unit": unit,
            "raw_locator": f"Monthly Prices!R{first - 1}C{j + 1}",
        }
        for j, (sid, name, unit) in cols.items()
    ]
    return _observations(obs, row), _frame(defs, row, _DEF_IN)


def _worldbank(blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
    if str(row["dataset_id"]) != "cmo_historical_monthly":
        return  # the commodity-markets page only carries the link to the workbook
    obs, defs = parse_worldbank_cmo(blob, row)
    yield Parsed("observation", "cmo_historical_monthly", obs)
    yield Parsed("definition", "cmo_historical_monthly", defs)


# ------------------------------------------------------------------------------------------------ EIA
# `hist_xls/<KEY>.xls`: sheet "Data 1" = a title row, `Sourcekey | <KEY>`, `Date | <name (unit)>`, then one row per
# date: an Excel date serial and a value. The unit is the parenthesis at the end of the name.


def parse_eia(blob: bytes, row: dict[str, Any]) -> tuple[pl.DataFrame, pl.DataFrame]:
    import xlrd  # pyright: ignore[reportMissingTypeStubs]

    wb = xlrd.open_workbook(file_contents=blob)
    sh = wb.sheet_by_name("Data 1")
    rows = [sh.row_values(i) for i in range(sh.nrows)]
    if len(rows) < 4 or rows[1][0] != "Sourcekey" or rows[2][0] != "Date":
        raise LayoutError(f"EIA: unexpected header rows {rows[:3]}")
    obs: list[dict[str, Any]] = []
    defs: list[dict[str, Any]] = []
    for j in range(1, sh.ncols):
        key, name = str(rows[1][j]), str(rows[2][j])
        unit = re.search(r"\(([^()]*)\)\s*$", name)
        if not key or unit is None:
            raise LayoutError(f"EIA: column {j} without key or unit: {key!r} {name!r}")
        sid = f"eia:{key}"
        defs.append(
            {
                "series_id": sid,
                "source_code": key,
                "name": name,
                "frequency": "D",
                "frequency_text": "daily (one row per published date)",
                "unit": unit.group(1),
                "raw_locator": f"Data 1!R3C{j + 1}",
            }
        )
        for i in range(3, sh.nrows):
            if sh.cell_type(i, 0) != xlrd.XL_CELL_DATE:  # pyright: ignore[reportUnknownMemberType]
                raise LayoutError(f"EIA row {i + 1}: date cell type {sh.cell_type(i, 0)}")
            day = xlrd.xldate_as_datetime(float(rows[i][0]), wb.datemode).date()  # pyright: ignore[reportUnknownMemberType]
            v = rows[i][j]
            if v == "":
                continue  # no price that day in this column
            text, norm = _xlsx_number(v)
            obs.append(
                {
                    "series_id": sid,
                    "vt_date": day,
                    "vt_until": None,
                    "period_text": day.isoformat(),
                    "value_text": text,
                    "value_norm": norm,
                    "raw_locator": f"Data 1!R{i + 1}C{j + 1}",
                }
            )
    return _observations(obs, row), _frame(defs, row, _DEF_IN)


# ------------------------------------------------------------------------------------------------ IMF
# PCPS in SDMX-ML structure-specific data: <Series COUNTRY INDICATOR DATA_TRANSFORMATION FREQUENCY SCALE> holding
# <Obs TIME_PERIOD="2010-M05" OBS_VALUE=…>. The payload names no unit: the indicator code is the unit code, labelled
# from IMF's CL_PCPS_INDICATOR (e.g. "Beef, US cents per pound, Unit prices").


def _imf_period(text: str, freq: str) -> date:
    if freq == "M":
        y, m = text.split("-M")
        return date(int(y), int(m), 1)
    if freq == "Q":
        y, q = text.split("-Q")
        return date(int(y), 3 * int(q) - 2, 1)
    if freq == "A":
        return date(int(text), 1, 1)
    raise LayoutError(f"IMF period {text!r} of frequency {freq}")


def parse_imf(blob: bytes, row: dict[str, Any]) -> tuple[pl.DataFrame, pl.DataFrame]:
    import xml.etree.ElementTree as ET

    root = ET.fromstring(blob)
    obs: list[dict[str, Any]] = []
    defs: list[dict[str, Any]] = []
    flow = re.search(r"/data/([A-Z_]+)/", _url(row))
    for n, s in enumerate((e for e in root.iter() if e.tag.split("}")[-1] == "Series"), start=1):
        a = s.attrib
        need = ("COUNTRY", "INDICATOR", "DATA_TRANSFORMATION", "FREQUENCY")
        if any(k not in a for k in need) or a["FREQUENCY"] not in SDMX_FREQ:
            raise LayoutError(f"IMF series {n}: attributes {a}")
        code = ".".join([flow.group(1) if flow else "IMF", *(a[k] for k in need)])
        sid = f"imf:{code}"
        unit = a["INDICATOR"] + ("" if a.get("SCALE", "0") == "0" else f" x10^{a['SCALE']}")
        defs.append(
            {
                "series_id": sid,
                "source_code": code,
                "name": f"{a['INDICATOR']} ({a['COUNTRY']}, {a['DATA_TRANSFORMATION']})",
                "frequency": SDMX_FREQ[a["FREQUENCY"]],
                "frequency_text": a["FREQUENCY"],
                "unit": unit,
                "raw_locator": f"Series[{n}]",
            }
        )
        for k, o in enumerate(s, start=1):
            obs.append(
                {
                    "series_id": sid,
                    "vt_date": _imf_period(o.attrib["TIME_PERIOD"], a["FREQUENCY"]),
                    "vt_until": None,
                    "period_text": o.attrib["TIME_PERIOD"],
                    "value_text": o.attrib.get("OBS_VALUE", ""),
                    "raw_locator": f"Series[{n}]/Obs[{k}]",
                }
            )
    if not defs:
        raise LayoutError("IMF: no Series in the payload")
    return _observations(obs, row), _frame(defs, row, _DEF_IN)


def _imf(blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
    ds = str(row["dataset_id"])
    if ds.startswith("codelist_"):
        yield Parsed("unit_label", ds, parse_sdmx_codelist(blob, row, "CL_PCPS_INDICATOR"))
        return
    obs, defs = parse_imf(blob, row)
    yield Parsed("observation", ds, obs)
    yield Parsed("definition", ds, defs)


def _pair(parse: Any) -> Any:
    def payload(blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
        obs, defs = parse(blob, row)
        yield Parsed("observation", str(row["dataset_id"]), obs)
        yield Parsed("definition", str(row["dataset_id"]), defs)

    return payload


# source_id -> payload parser, for the connectors generated from the context catalogue (ingest/context.py)
CATALOGUE_PARSERS: dict[str, Any] = {
    "us_treasury": _pair(parse_us_treasury),
    "nyfed": _pair(parse_nyfed),
    "cboe": _pair(parse_cboe),
    "worldbank_cmo": _worldbank,
    "eia": _pair(parse_eia),
    "imf": _imf,
    "ecb": _sdmx("ecb"),
    "bis": _sdmx("bis"),
    "oecd": _sdmx("oecd"),
}


# ------------------------------------------------------------------------------------------------ core


def _period(freq: pl.Expr, d: pl.Expr, until: pl.Expr) -> list[pl.Expr]:
    month_end = d.dt.month_end()
    q_end = d.dt.offset_by("2mo").dt.month_end()
    y_end = d.dt.offset_by("11mo").dt.month_end()
    m3_start = d.dt.offset_by("-2mo")
    ref = (
        pl.when((freq == "D") & until.is_not_null())
        .then(d.dt.strftime("%Y-%m-%d") + ".." + until.dt.offset_by("-1d").dt.strftime("%Y-%m-%d"))
        .when(freq == "D")
        .then(d.dt.strftime("%Y-%m-%d"))
        .when(freq == "M")
        .then(d.dt.strftime("%Y-%m"))
        .when(freq == "Q")
        .then(d.dt.strftime("%Y") + "Q" + ((d.dt.month() + 2) // 3).cast(pl.String))
        .when(freq == "A")
        .then(d.dt.strftime("%Y"))
        .when(freq == "M3")
        .then(m3_start.dt.strftime("%Y-%m") + ".." + d.dt.strftime("%Y-%m"))
    )
    start = pl.when(freq == "M3").then(m3_start).otherwise(d)
    end = (
        pl.when(freq == "D")
        .then(pl.when(until.is_not_null()).then(until.dt.offset_by("-1d")).otherwise(d))
        .when(freq.is_in(["M", "M3"]))
        .then(month_end)
        .when(freq == "Q")
        .then(q_end)
        .when(freq == "A")
        .then(y_end)
    )
    aligned = (
        (freq == "D")
        | ((freq.is_in(["M", "M3"])) & (d.dt.day() == 1))
        | ((freq == "Q") & (d.dt.day() == 1) & d.dt.month().is_in([1, 4, 7, 10]))
        | ((freq == "A") & (d.dt.day() == 1) & (d.dt.month() == 1))
    )
    return [ref.alias("vt_reference"), start.alias("vt_start"), end.alias("vt_end"), aligned.alias("_aligned")]


def latest_definitions(defs: pl.DataFrame) -> pl.DataFrame:
    return defs.sort("kt_first_seen_at").unique("series_id", keep="last", maintain_order=True).sort("series_id")


def label_units(defs: pl.DataFrame, labels: pl.DataFrame) -> pl.DataFrame:
    """`PCPA` -> `Percent per annum (PCPA)`, `PC x10^3` -> `Percent (PC) x10^3`, from the latest codelist payload."""
    lab = labels.sort("kt_first_seen_at").unique("code", keep="last").select("code", "label")
    code = pl.col("unit").str.split(" x10^").list.first()
    rest = pl.col("unit").str.strip_prefix(code)
    out = defs.with_columns(code.alias("_code"), rest.alias("_rest")).join(
        lab, left_on="_code", right_on="code", how="left"
    )
    return out.with_columns(
        pl.when(pl.col("label").is_not_null())
        .then(pl.col("label") + " (" + pl.col("_code") + ")" + pl.col("_rest"))
        .otherwise(pl.col("unit"))
        .alias("unit")
    ).select(defs.columns)


def versions(obs: pl.DataFrame) -> pl.DataFrame:
    """Keep the first row of each (series, period) and each later row whose value differs from the one before it.
    A period is its date and, where the source states one, its end (SGS TR: one start date, several periods)."""
    key = ("series_id", "vt_date", "vt_until")
    o = obs.filter(pl.col("value").is_not_null()).sort(*key, "kt_first_seen_at", "raw_sha256", nulls_last=True)
    prev = pl.col("value").shift(1).over(key)
    changed = prev.is_null() | (pl.col("value") != prev)
    o = o.filter(changed)
    return o.with_columns(pl.int_range(1, pl.len() + 1, dtype=pl.Int32).over(key).alias("version"))


def build_core(zones: Zones, source_id: str, run: IngestRun | None = None) -> tuple[int, int]:
    """Rebuild this source's partition of core `series_observation` and `series_definition` from its staging.
    Returns (rows written, rows quarantined)."""
    obs = read_parquet_dir(zones.staging / source_id / "observation")
    defs = read_parquet_dir(zones.staging / source_id / "definition")
    out_obs = zones.core / "series_observation" / f"source={source_id}.parquet"
    out_def = zones.core / "series_definition" / f"source={source_id}.parquet"
    q = zones.quarantine / "core" / "series_observation" / f"source={source_id}.parquet"
    if obs is None:
        return 0, 0
    latest = latest_definitions(defs) if defs is not None else pl.DataFrame(schema=DEFINITION.schema())
    labels = read_parquet_dir(zones.staging / source_id / "unit_label")
    if labels is not None and latest.height:
        latest = label_units(latest, labels)
    write_parquet(SERIES_DEFINITION.conform(latest), out_def)
    v = versions(obs).join(latest.select("series_id", "frequency", "unit"), on="series_id", how="left")
    v = v.with_columns(*_period(pl.col("frequency"), pl.col("vt_date"), pl.col("vt_until")))
    v = v.with_columns(
        pl.when(pl.col("_aligned")).then(pl.col("vt_reference")).alias("vt_reference"),
        pl.lit(None, dtype=KT).alias("kt_published_at"),
    ).drop("_aligned")
    # a series without a definition, or a date off its frequency's grid, breaks a not-null rule: quarantined
    full = v.with_columns(
        pl.col("frequency").fill_null(""),
    )
    good, bad = SERIES_OBSERVATION.split(full.select(SERIES_OBSERVATION.names))
    write_parquet(good.sort("series_id", "vt_start", "version"), out_obs)
    if bad.height:
        write_parquet(bad, q)
    else:
        q.unlink(missing_ok=True)
    if run is not None:
        run.count("core.series_observation", in_=full.height, out=good.height, quarantined=bad.height)
    return good.height, bad.height


CONTRACTS: dict[str, Contract] = {"observation": OBSERVATION, "definition": DEFINITION, "unit_label": UNIT_LABEL}
