"""Parsers for the ANBIMA free files archived daily (docs/sources/anbima_*.md), source-shaped staging tables.

All files are Latin-1, `@`- or `;`-separated, decimal comma, thousands dot, `dd/mm/yyyy` dates (titulos: `YYYYMMDD`).
Numbers become exact `Decimal`s (never floats); an empty field, `--` or `N/D` is a null. Rates are % a.a.
(business-day base, 252) unless a column says otherwise.

| source | dataset (staging) | one row is |
|---|---|---|
| anbima_ettj | `parameter` | a Svensson curve (PREFIXADOS, IPCA) of a day: beta1-4, lambda1-2 |
| | `vertex` | a business-day vertex of the day: ETTJ IPCA (real), ETTJ PREF, implied inflation |
| | `circular_vertex` | a vertex of the PREFIXADOS curve of Circular 3.361 |
| | `bond_error` | the fit error of one federal bond |
| anbima_vna | `vna` | the VNA of NTN-B, NTN-C or LFT on a day |
| anbima_debentures | `debenture_rate` | the secondary-market rates and price of one debenture on a day |
| anbima_titulos_publicos | `bond_rate` | the indicative rates and PU of one federal bond maturity on a day |
| anbima_projecoes | `indicator` | one figure of the 'Quadro Indicadores' page (latest values only) |

Svensson check (golden test): with t = business days / 252 years,
r(t) = b1 + b2 f1 + b3 (f1 - e^-l1 t) + b4 (f2 - e^-l2 t), f_i = (1 - e^-li t) / (li t),
reproduces the published vertices (PREF 252: 14.1829,
IPCA 252: 6.3470) to 0.0002 pp, so betas are annual rates as fractions and lambdas multiply t in years.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from typing import Any

import polars as pl

from fin.ingest.base import NotData, Parsed
from fin.schema import Column, Contract, Rule

NUM = pl.Decimal(38, 24)  # betas carry 16-18 decimals
RATE = pl.Decimal(38, 12)
NULLS = frozenset({"", "--", "N/D"})


class LayoutError(ValueError):
    pass


def _text(blob: bytes) -> list[str]:
    return [ln for ln in blob.decode("latin-1").replace("\r\n", "\n").split("\n")]


def _num(text: str | None, scale: int = 24) -> Decimal | None:
    """`1.243,905` -> 1243.905; `7,17E-02` -> 0.0717 exactly; '', `--`, `N/D` -> None. More than `scale`
    decimals is refused (a cast would round silently)."""
    if text is None or text.strip() in NULLS:
        return None
    try:
        d = Decimal(text.strip().replace(".", "").replace(",", "."))
    except InvalidOperation as e:
        raise LayoutError(f"not a number: {text!r}") from e
    exp = d.as_tuple().exponent
    if not d.is_finite() or (isinstance(exp, int) and -exp > scale):
        raise LayoutError(f"{text!r} is not a finite number with at most {scale} decimals")
    return d


def _dmy(text: str) -> date:
    d, m, y = text.strip().split("/")
    return date(int(y), int(m), int(d))


def _date_or_none(text: str | None) -> date | None:
    return None if text is None or text.strip() in NULLS else _dmy(text)


def _build(rows: list[dict[str, Any]], contract: Contract, row: dict[str, Any]) -> pl.DataFrame:
    schema = {c.name: c.dtype for c in contract.columns} | {"raw_locator": pl.String}
    df = pl.DataFrame(rows, schema=schema, orient="row")
    return df.with_columns(
        pl.lit(row["raw_sha256"]).alias("raw_sha256"), pl.lit(row["ingest_run_id"]).alias("ingest_run_id")
    )


def _reference_date(row: dict[str, Any]) -> date:
    """Files that do not state their date (debentures): the manifest's `source_reference_date`."""
    d = row.get("source_reference_date")
    if isinstance(d, date):
        return d
    raise LayoutError("this file does not state its date and the manifest row has no source_reference_date")


# ------------------------------------------------------------------------------------------------ ETTJ

PARAMETER = Contract(
    table="staging.anbima_ettj.parameter",
    version=1,
    description="Svensson parameters of ANBIMA's estimated zero curve for a day (PREFIXADOS and IPCA).",
    columns=(
        Column("ref_date", pl.Date, "Data de Referencia", "data de referência", "date", nullable=False),
        Column("curve", pl.String, "PREFIXADOS (nominal) or IPCA (real)", "curva", nullable=False),
        Column("beta1", NUM, "Beta 1: long-run level", "beta 1", "annual rate as a fraction (0.14 = 14%)"),
        Column("beta2", NUM, "Beta 2", "beta 2", "annual rate as a fraction"),
        Column("beta3", NUM, "Beta 3", "beta 3", "annual rate as a fraction"),
        Column("beta4", NUM, "Beta 4", "beta 4", "annual rate as a fraction"),
        Column("lambda1", NUM, "Lambda 1: decay; multiplies t in years", "lambda 1", "1/year (t = business days/252)"),
        Column("lambda2", NUM, "Lambda 2: decay; multiplies t in years", "lambda 2", "1/year (t = business days/252)"),
    ),
    rules=(Rule("curve_known", pl.col("curve").is_in(["PREFIXADOS", "IPCA"])),),
    key=("ref_date", "curve", "raw_sha256"),
)
VERTEX = Contract(
    table="staging.anbima_ettj.vertex",
    version=1,
    description="ETTJ at business-day vertices: real (IPCA) and nominal (PREF) zero rates and implied inflation.",
    columns=(
        Column("ref_date", pl.Date, "Data de Referencia", "data de referência", "date", nullable=False),
        Column("business_days", pl.Int32, "vertex in business days", "vértice", "business days (252/yr)", False),
        Column("ettj_ipca_pct", RATE, "ETTJ IPCA: real zero rate", "ETTJ IPCA", "% a.a."),
        Column("ettj_pref_pct", RATE, "ETTJ PREF: nominal zero rate (empty beyond ~2,520 du)", "ETTJ PREF", "% a.a."),
        Column(
            "implied_inflation_pct", RATE, "Inflação Implícita (empty beyond ~2,520 du)", "inflação implícita", "% a.a."
        ),
    ),
    rules=(Rule("vertex_positive", pl.col("business_days") > 0),),
    key=("ref_date", "business_days", "raw_sha256"),
)
CIRCULAR_VERTEX = Contract(
    table="staging.anbima_ettj.circular_vertex",
    version=1,
    description="PREFIXADOS curve at the vertices of Circular 3.361.",
    columns=(
        Column("ref_date", pl.Date, "Data de Referencia", "data de referência", "date", nullable=False),
        Column("business_days", pl.Int32, "vertex in business days", "vértice", "business days (252/yr)", False),
        Column("rate_pct", RATE, "Taxa (%a.a.)", "taxa", "% a.a.", False),
    ),
    key=("ref_date", "business_days", "raw_sha256"),
)
BOND_ERROR = Contract(
    table="staging.anbima_ettj.bond_error",
    version=1,
    description="Fit error of the curve at each federal bond used (Erro Título a Título).",
    columns=(
        Column("ref_date", pl.Date, "Data de Referencia", "data de referência", "date", nullable=False),
        Column("bond_type", pl.String, "Titulo: LTN, NTN-F, NTN-B", "título", nullable=False),
        Column("selic_code", pl.String, "Código SELIC of the bond family", "código SELIC", nullable=False),
        Column("maturity_date", pl.Date, "Vencimento", "vencimento", "date", nullable=False),
        Column("error_pct", RATE, "Erro (%a.a.): fitted minus observed rate", "erro", "% a.a.", False),
    ),
    key=("ref_date", "bond_type", "maturity_date", "raw_sha256"),
)
ETTJ_CONTRACTS = {
    "parameter": PARAMETER,
    "vertex": VERTEX,
    "circular_vertex": CIRCULAR_VERTEX,
    "bond_error": BOND_ERROR,
}


def parse_ettj(blob: bytes, row: dict[str, Any]) -> dict[str, pl.DataFrame]:
    """`CurvaZero_ddmmyyyy.txt`: line = `<record type>@field@...` (docs/sources/anbima_ettj.md §3)."""
    lines = _text(blob)
    ref: date | None = None
    out: dict[str, list[dict[str, Any]]] = {k: [] for k in ETTJ_CONTRACTS}
    for i, ln in enumerate(lines):
        f = ln.rstrip().split("@")
        loc = f"line={i + 1}"
        if f[0] == "0" and len(f) == 3 and f[1].startswith("Data de Refer"):
            ref = _dmy(f[2])
        elif f[0] == "1" and f[1] not in ("Grupo",):
            if len(f) != 8 or ref is None:
                raise LayoutError(f"{loc}: expected a date line then 7 fields, got {ln!r}")
            b = [_num(x) for x in f[2:]]
            out["parameter"].append(
                dict(
                    zip(
                        ("ref_date", "curve", "beta1", "beta2", "beta3", "beta4", "lambda1", "lambda2"),
                        (ref, f[1], *b),
                        strict=True,
                    )
                )
                | {"raw_locator": loc}
            )
        elif f[0] == "2" and f[1].replace(".", "").isdigit():
            if ref is None or len(f) != 5:
                raise LayoutError(f"{loc}: unexpected vertex line {ln!r}")
            out["vertex"].append(
                {
                    "ref_date": ref,
                    "business_days": int(f[1].replace(".", "")),
                    "ettj_ipca_pct": _num(f[2], 12),
                    "ettj_pref_pct": _num(f[3], 12),
                    "implied_inflation_pct": _num(f[4], 12),
                    "raw_locator": loc,
                }
            )
        elif f[0] == "3" and f[1].replace(".", "").isdigit():
            if ref is None or len(f) != 3:
                raise LayoutError(f"{loc}: unexpected circular vertex line {ln!r}")
            out["circular_vertex"].append(
                {
                    "ref_date": ref,
                    "business_days": int(f[1].replace(".", "")),
                    "rate_pct": _num(f[2], 12),
                    "raw_locator": loc,
                }
            )
        elif f[0] == "4" and f[1] != "Titulo" and len(f) > 2:
            if ref is None or len(f) != 5:
                raise LayoutError(f"{loc}: unexpected bond error line {ln!r}")
            out["bond_error"].append(
                {
                    "ref_date": ref,
                    "bond_type": f[1],
                    "selic_code": f[2],
                    "maturity_date": _dmy(f[3]),
                    "error_pct": _num(f[4], 12),
                    "raw_locator": loc,
                }
            )
    if ref is None:
        raise NotData("ANBIMA ETTJ: no 'Data de Referencia' line (out-of-window stub)")
    return {k: _build(v, ETTJ_CONTRACTS[k], row) for k, v in out.items()}


def parse_ettj_payload(blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
    frames = parse_ettj(blob, row)
    for name, df in frames.items():
        yield Parsed(name, f"ref_date={df['ref_date'][0]}" if df.height else "empty", df)


# ------------------------------------------------------------------------------------------------ VNA

VNA = Contract(
    table="staging.anbima_vna.vna",
    version=1,
    description="ANBIMA's VNA (valor nominal atualizado) of NTN-B, NTN-C and LFT on a day.",
    columns=(
        Column("ref_date", pl.Date, "Data de Referência", "data de referência", "date", nullable=False),
        Column("bond_type", pl.String, "Titulo: NTN-B, NTN-C, LFT", "título", nullable=False),
        Column("selic_code", pl.String, "Código Selic (760199, 770100, 210100)", "código SELIC", nullable=False),
        Column("vna_brl", RATE, "VNA", "VNA", "BRL per bond (updated nominal value)", False),
        Column(
            "index_pct",
            RATE,
            "Índice: monthly % applied (IPCA for NTN-B, IGP-M for NTN-C); LFT row: Selic % a.a.",
            "índice",
            "% per month (NTN-B/C); % a.a. (LFT)",
            False,
        ),
        Column("index_status", pl.String, "Ref: F = closed index, P = ANBIMA projection; null for LFT", "ref"),
        Column("valid_from", pl.Date, "Válido a partir de; null for LFT", "válido a partir de", "date"),
    ),
    rules=(
        Rule("vna_positive", pl.col("vna_brl") > 0),
        Rule("status_known", pl.col("index_status").is_null() | pl.col("index_status").is_in(["F", "P"])),
    ),
    key=("ref_date", "bond_type", "raw_sha256"),
)


def parse_vna(blob: bytes, row: dict[str, Any]) -> pl.DataFrame:
    lines = _text(blob)
    ref: date | None = None
    rows: list[dict[str, Any]] = []
    in_table = False
    for i, ln in enumerate(lines):
        if ln.startswith("Data de Refer"):
            ref = _dmy(ln.split(":")[1])
        elif ln.startswith("Titulo;"):
            in_table = True
        elif in_table and ln.strip():
            f = ln.rstrip().split(";")
            if ref is None or len(f) not in (4, 6):
                raise LayoutError(f"line={i + 1}: unexpected VNA line {ln!r}")
            rows.append(
                {
                    "ref_date": ref,
                    "bond_type": f[0],
                    "selic_code": f[1],
                    "vna_brl": _num(f[2], 12),
                    "index_pct": _num(f[3], 12),
                    "index_status": f[4] if len(f) == 6 else None,
                    "valid_from": _dmy(f[5]) if len(f) == 6 else None,
                    "raw_locator": f"line={i + 1}",
                }
            )
    if ref is None:
        raise NotData("ANBIMA VNA: no 'Data de Referência' line ('Não existem registros' stub)")
    return _build(rows, VNA, row)


def parse_vna_payload(blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
    df = parse_vna(blob, row)
    yield Parsed("vna", f"ref_date={df['ref_date'][0]}" if df.height else "empty", df)


# ------------------------------------------------------------------------------------------------ debentures

DEBENTURE_RATE = Contract(
    table="staging.anbima_debentures.debenture_rate",
    version=1,
    description="Secondary-market indicative rates and PU of a debenture on a day (ANBIMA).",
    columns=(
        Column(
            "ref_date", pl.Date, "reference date (from the manifest: the file does not state it)", "data", "date", False
        ),
        Column("ticker", pl.String, "Código (B3/Cetip ticker)", "código", nullable=False),
        Column("issuer_name", pl.String, "Nome without the (*) markers", "nome"),
        Column("name_marks", pl.String, "the (*) / (**) footnote markers of Nome, as written", "marcas"),
        Column("maturity_date", pl.Date, "Repac./Venc.", "vencimento", "date"),
        Column(
            "indexation_text",
            pl.String,
            "Índice/Correção as written (DI + 1,6%, IPCA + 6,5%, 112% do DI...)",
            "indexador",
        ),
        Column("indexer", pl.String, "DI, IPCA, IGP-M or PRE, read from indexation_text", "indexador (lido)"),
        Column("spread_pct", RATE, "fixed spread or prefixed rate in indexation_text", "spread", "% a.a."),
        Column("percent_of_di", RATE, "'N% do DI': N", "% do DI", "% of DI"),
        Column("bid_rate_pct", RATE, "Taxa de Compra", "taxa de compra", "% a.a."),
        Column("ask_rate_pct", RATE, "Taxa de Venda", "taxa de venda", "% a.a."),
        Column("indicative_rate_pct", RATE, "Taxa Indicativa", "taxa indicativa", "% a.a."),
        Column("std_dev", NUM, "Desvio Padrão (unit not stated in the file)", "desvio padrão", "as published"),
        Column("indicative_min_pct", RATE, "Intervalo Indicativo Mínimo", "intervalo mínimo", "% a.a."),
        Column("indicative_max_pct", RATE, "Intervalo Indicativo Máximo", "intervalo máximo", "% a.a."),
        Column("price_brl", RATE, "PU", "PU", "BRL per debenture"),
        Column("price_pct_par", RATE, "% PU Par / % VNE", "% do PU par / VNE", "% of par value / VNE"),
        Column("duration_bdays", RATE, "Duration", "duration", "business days"),
        Column(
            "reune_pct", RATE, "% Reune (meaning not documented by ANBIMA in the file)", "% reune", "% as published"
        ),
        Column(
            "reference_ntnb_maturity",
            pl.Date,
            "Referência NTN-B: maturity of the reference NTN-B",
            "NTN-B de referência",
            "date",
        ),
    ),
    rules=(
        Rule("price_positive", pl.col("price_brl").is_null() | (pl.col("price_brl") > 0)),
        Rule("indexer_known", pl.col("indexer").is_in(["DI", "IPCA", "IGP-M", "PRE"])),
    ),
    key=("ref_date", "ticker", "raw_sha256"),
)
_INDEX_RE = re.compile(
    r"^(?:(?P<ix>DI|IPCA)\s*\+\s*(?P<sp>[\d.,]+)%|(?P<pct>[\d.,]+)%\s*do\s*DI|PREFIXADO\s+(?P<pre>[\d.,]+)%|(?P<igpm>IGP-M))$"
)
_MARKS = re.compile(r"((?:\s*\(\*+\))+)\s*$")


def _indexation(text: str) -> tuple[str, Decimal | None, Decimal | None]:
    m = _INDEX_RE.match(text.strip())
    if not m:
        raise LayoutError(f"unknown Índice/Correção: {text!r}")
    if m["ix"]:
        return m["ix"], _num(m["sp"], 12), None
    if m["pct"]:
        return "DI", None, _num(m["pct"], 12)
    if m["pre"]:
        return "PRE", _num(m["pre"], 12), None
    return "IGP-M", None, None


def parse_debentures(blob: bytes, row: dict[str, Any]) -> pl.DataFrame:
    ref = _reference_date(row)
    lines = _text(blob)
    try:
        h = next(i for i, ln in enumerate(lines) if ln.startswith("C") and "@Nome@" in ln)
    except StopIteration as e:
        raise NotData("ANBIMA debentures: no header line") from e
    rows: list[dict[str, Any]] = []
    for i in range(h + 1, len(lines)):
        ln = lines[i]
        if not ln.strip():
            continue
        f = ln.rstrip("\r").split("@")
        if len(f) != 15:
            raise LayoutError(f"line={i + 1}: expected 15 fields, got {len(f)}")
        m = _MARKS.search(f[1])
        ix, spread, pct = _indexation(f[3])
        rows.append(
            {
                "ref_date": ref,
                "ticker": f[0],
                "issuer_name": (f[1][: m.start()] if m else f[1]).strip(),
                "name_marks": m.group(1).strip() if m else None,
                "maturity_date": _date_or_none(f[2]),
                "indexation_text": f[3],
                "indexer": ix,
                "spread_pct": spread,
                "percent_of_di": pct,
                "bid_rate_pct": _num(f[4], 12),
                "ask_rate_pct": _num(f[5], 12),
                "indicative_rate_pct": _num(f[6], 12),
                "std_dev": _num(f[7]),
                "indicative_min_pct": _num(f[8], 12),
                "indicative_max_pct": _num(f[9], 12),
                "price_brl": _num(f[10], 12),
                "price_pct_par": _num(f[11], 12),
                "duration_bdays": _num(f[12], 12),
                "reune_pct": _num(f[13], 12),
                "reference_ntnb_maturity": _date_or_none(f[14]),
                "raw_locator": f"line={i + 1}",
            }
        )
    return _build(rows, DEBENTURE_RATE, row)


def parse_debentures_payload(blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
    df = parse_debentures(blob, row)
    yield Parsed("debenture_rate", f"ref_date={_reference_date(row)}", df)


# ------------------------------------------------------------------------------------------------ titulos publicos

BOND_RATE = Contract(
    table="staging.anbima_titulos_publicos.bond_rate",
    version=1,
    description="ANBIMA indicative rates and PU of one federal bond maturity on a day (secondary market).",
    columns=(
        Column("ref_date", pl.Date, "Data Referencia", "data de referência", "date", nullable=False),
        Column("bond_type", pl.String, "Titulo: LTN, NTN-F, NTN-B, NTN-C, LFT", "título", nullable=False),
        Column("selic_code", pl.String, "Codigo SELIC", "código SELIC", nullable=False),
        Column("issue_date", pl.Date, "Data Base/Emissao", "data base/emissão", "date"),
        Column("maturity_date", pl.Date, "Data Vencimento", "vencimento", "date", nullable=False),
        Column("buy_rate_pct", RATE, "Tx. Compra", "taxa de compra", "% a.a. (252; LFT: spread over Selic)"),
        Column("sell_rate_pct", RATE, "Tx. Venda", "taxa de venda", "% a.a. (252; LFT: spread over Selic)"),
        Column(
            "indicative_rate_pct", RATE, "Tx. Indicativas", "taxa indicativa", "% a.a. (252; LFT: spread over Selic)"
        ),
        Column("price_brl", RATE, "PU", "PU", "BRL per bond"),
        Column("std_dev", NUM, "Desvio padrao (unit not stated in the file)", "desvio padrão", "as published"),
        Column("lower_d0_pct", RATE, "Interv. Ind. Inf. (D0)", "intervalo inferior D0", "% a.a."),
        Column("upper_d0_pct", RATE, "Interv. Ind. Sup. (D0)", "intervalo superior D0", "% a.a."),
        Column("lower_d1_pct", RATE, "Interv. Ind. Inf. (D+1)", "intervalo inferior D+1", "% a.a."),
        Column("upper_d1_pct", RATE, "Interv. Ind. Sup. (D+1)", "intervalo superior D+1", "% a.a."),
        Column("criterion", pl.String, "Criterio (Calculado, ...)", "critério"),
    ),
    rules=(
        Rule("price_positive", pl.col("price_brl").is_null() | (pl.col("price_brl") > 0)),
        Rule("maturity_after_issue", pl.col("issue_date").is_null() | (pl.col("maturity_date") > pl.col("issue_date"))),
    ),
    key=("ref_date", "bond_type", "maturity_date", "raw_sha256"),
)


def _ymd(text: str) -> date:
    return date(int(text[:4]), int(text[4:6]), int(text[6:8]))


def parse_titulos(blob: bytes, row: dict[str, Any]) -> pl.DataFrame:
    lines = _text(blob)
    try:
        h = next(i for i, ln in enumerate(lines) if ln.startswith("Titulo@"))
    except StopIteration as e:
        raise NotData("ANBIMA titulos publicos: no header line") from e
    rows: list[dict[str, Any]] = []
    for i in range(h + 1, len(lines)):
        ln = lines[i]
        if not ln.strip():
            continue
        f = ln.rstrip("\r").split("@")
        if len(f) != 15:
            raise LayoutError(f"line={i + 1}: expected 15 fields, got {len(f)}")
        rows.append(
            {
                "ref_date": _ymd(f[1]),
                "bond_type": f[0],
                "selic_code": f[2],
                "issue_date": _ymd(f[3]) if f[3].strip() not in NULLS else None,
                "maturity_date": _ymd(f[4]),
                "buy_rate_pct": _num(f[5], 12),
                "sell_rate_pct": _num(f[6], 12),
                "indicative_rate_pct": _num(f[7], 12),
                "price_brl": _num(f[8], 12),
                "std_dev": _num(f[9]),
                "lower_d0_pct": _num(f[10], 12),
                "upper_d0_pct": _num(f[11], 12),
                "lower_d1_pct": _num(f[12], 12),
                "upper_d1_pct": _num(f[13], 12),
                "criterion": f[14].strip() or None,
                "raw_locator": f"line={i + 1}",
            }
        )
    return _build(rows, BOND_RATE, row)


def parse_titulos_payload(blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
    # the .xls twin carries the same figures: it is archived (raw is immutable) but not parsed twice
    if str(row["dataset_id"]) != "ms_txt":
        return
    df = parse_titulos(blob, row)
    yield Parsed("bond_rate", f"ref_date={df['ref_date'][0]}" if df.height else "empty", df)


# ------------------------------------------------------------------------------------------------ projecoes (HTML)

INDICATOR = Contract(
    table="staging.anbima_projecoes.indicator",
    version=1,
    description="One figure of ANBIMA's 'Quadro Indicadores' page: the latest values only, as of `updated_at`.",
    columns=(
        Column(
            "updated_at",
            pl.Datetime("us"),
            "Data e Hora da Última Atualização (Brasília time, no zone)",
            "atualizado em",
            "timestamp (BRT, naive)",
            False,
        ),
        Column("indicator", pl.String, "stable code read from the row label", "indicador", nullable=False),
        Column("label", pl.String, "the row label as published, footnote digit removed", "rótulo"),
        Column(
            "observation_date",
            pl.Date,
            "the figure's own date (column Data); null for monthly index rows",
            "data",
            "date",
        ),
        Column(
            "period",
            pl.String,
            "reference month as written (out/26) for index, variation and projection rows",
            "período",
        ),
        Column("value", RATE, "the figure", "valor", "see `unit`", False),
        Column("unit", pl.String, "unit of the figure", "unidade", nullable=False),
    ),
    rules=(Rule("indicator_known", pl.col("indicator").str.len_chars() > 0),),
    key=("indicator", "observation_date", "period", "raw_sha256"),
)
# row label (footnote digit removed) -> (code, unit); the column header of the section fixes the unit otherwise
_LABELS: dict[str, tuple[str, str]] = {
    "Estimativa SELIC": ("selic_estimate", "% a.a."),
    "Taxa SELIC do BC": ("selic_bcb", "% a.a."),
    "DI-B3": ("di_b3", "% a.a."),
    "Dolar Comercial Compra": ("usd_buy", "BRL per USD"),
    "Dólar Comercial Venda": ("usd_sell", "BRL per USD"),
    "Euro Compra": ("eur_buy", "BRL per EUR"),
    "Euro Venda": ("eur_sell", "BRL per EUR"),
    "TR": ("tr", "% (monthly yield, month to date)"),
    "TBF": ("tbf", "% (monthly yield, month to date)"),
    "FDS": ("fds_quota", "BRL per quota"),
}
_PERIOD = re.compile(r"\(([a-zç]{3}/\d\d)\)")


class _Rows(HTMLParser):
    """Rows of cells (text only) of every table of the page; `rowspan` cells are kept in their own row."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._cell: list[str] | None = None
        self._row: list[str] | None = None
        self.text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._row = []
        elif tag == "td" and self._row is not None:
            self._cell = []
        elif tag == "sub" and self._cell is not None:
            self._cell.append("\x00")  # footnote marker: dropped with the digit that follows

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self._cell is not None and self._row is not None:
            self._row.append(re.sub(r"\x00\s*\d*", "", "".join(self._cell)).replace("\xa0", " ").strip())
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None

    def handle_data(self, data: str) -> None:
        self.text.append(data)
        if self._cell is not None:
            self._cell.append(data)


def parse_indicators(blob: bytes, row: dict[str, Any]) -> pl.DataFrame:
    page = blob.decode("latin-1")
    m = re.search(r"Data e Hora da .{0,12}ltima Atualiza.{0,6}o:\s*(\d\d/\d\d/\d{4})\s*-\s*(\d\d):(\d\d)", page)
    if not m:
        raise NotData("ANBIMA Quadro Indicadores: no update timestamp")
    parser = _Rows()
    parser.feed(page)
    d = _dmy(m[1])
    updated = datetime(d.year, d.month, d.day, int(m[2]), int(m[3]))  # noqa: DTZ001 (BRT, stored naive)
    rows: list[dict[str, Any]] = []
    last_label = ""
    for i, r in enumerate(parser.rows):
        if len(r) == 3:
            label, what, val = r
            last_label = label
        elif len(r) == 2:  # the second row of a rowspan label: (what, value)
            label, (what, val) = last_label, r
        else:
            continue
        if not re.fullmatch(r"-?[\d.]+(,\d+)?", val):  # section headers ('', 'Data', 'Taxa % a.a.') and notes
            continue
        period: str | None = None
        obs: date | None = None
        if label in _LABELS:
            code, unit = _LABELS[label]
            obs = _dmy(what)
        elif label.startswith(("IGP-M", "IPCA")):
            fam = "igpm" if label.startswith("IGP-M") else "ipca"
            pm = _PERIOD.search(label) or _PERIOD.search(what)
            period = pm[1] if pm else None
            if what.startswith("Número"):
                code, unit = f"{fam}_index", "index points (number index)"
            elif what.startswith("Var"):
                code, unit = f"{fam}_var_month", "% in the month"
            elif what.startswith("Proje"):
                code, unit = f"{fam}_projection", "% in the month (ANBIMA committee projection)"
            else:
                raise LayoutError(f"row {i}: unknown {label!r} / {what!r}")
        else:
            raise LayoutError(f"row {i}: unknown indicator {label!r}")
        rows.append(
            {
                "updated_at": updated,
                "indicator": code,
                "label": label if obs else f"{label} / {what}",
                "observation_date": obs,
                "period": period,
                "value": _num(val, 12),
                "unit": unit,
                "raw_locator": f"table_row={i + 1}",
            }
        )
    if not rows:
        raise LayoutError("ANBIMA Quadro Indicadores: no figures found")
    return _build(rows, INDICATOR, row)


def parse_indicators_payload(blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
    df = parse_indicators(blob, row)
    yield Parsed("indicator", f"updated={df['updated_at'][0]:%Y-%m-%d}", df)
