"""SND (debentures.com.br) payloads: debenture terms and secondary-market trade statistics.

See docs/sources/snd_debentures.md.

Both are Latin-1, CRLF, tab-separated exports with a banner above the header, verified against the archived raw
(2026-11-08). The header is checked column by column: any other layout raises (`LayoutError`).

`caracteristicas` (`emissoesdedebentures/caracteristicas_e.asp`): two banner lines and a blank, then the 85-column
header (names padded with spaces, `Unidade Monetaria` twice) and one row per debenture **and issuer**: a debenture
co-issued by two companies appears twice with the same code (9 codes, 2026-11-08). Dates are dd/mm/yyyy, `-` or empty
is no value. Quantities are zero-padded integers. Rates are decimal numbers written with a comma, except
`Percentual Multiplicador/Rentabilidade` and `Amortizacao - Taxa`, which use a point. No personal data: the columns
name companies, banks and trustees only.

`precos` (`mercadosecundario/precosdenegociacao_e.asp`): banner, blank, header, then one row per debenture and day:
date (d/m/yyyy), issuer, code, ISIN, quantity, number of trades (`-` before 2010), PU min/avg/max with a comma
decimal and point thousands, and `% PU da Curva` (`ND` when SND has no curve PU). A range without trades answers
"Não existe consulta para os itens selecionados.": a legitimate empty answer, parsed to nothing.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import polars as pl

from fin.ingest.base import NotData, Parsed
from fin.schema import Column, Contract, Rule

DEC = pl.Decimal(38, 12)
TERMS_FIRST_COLUMN = "Codigo do Ativo"
NO_DATA = "Não existe consulta"


class LayoutError(ValueError):
    pass


# (source header, staging column, kind, meaning, unit). Kinds: s text, d date (dd/mm/yyyy), i integer, n decimal.
TERMS_COLUMNS: tuple[tuple[str, str, str, str, str], ...] = (
    ("Codigo do Ativo", "ticker", "s", "debenture code (B3/Cetip), the key of SND", ""),
    ("Empresa", "issuer_name", "s", "issuer as written", ""),
    ("Serie", "series", "s", "series (UNI = single)", ""),
    ("Emissao", "issue_number", "s", "issue number within the issuer", ""),
    ("IPO", "ipo", "s", "Sim/Não, - when not stated", ""),
    ("Situacao", "situation", "s", "Registrado or Excluído", ""),
    ("ISIN", "isin", "s", "ISIN; null when blank; can be shared by several codes or a placeholder", ""),
    ("Registro CVM da Emissao", "cvm_issue_registry", "s", "CVM registry or exemption of the issue", ""),
    ("Data de Registro CVM da Emissao", "cvm_issue_registered_on", "d", "date of that registry", "date"),
    ("Registro CVM do Programa", "cvm_program_registry", "s", "CVM registry of the programme", ""),
    ("Data de Registro CVM do Programa", "cvm_program_registered_on", "d", "date of that registry", "date"),
    ("Data de Emissao", "issue_date", "d", "issue date", "date"),
    ("Data de Vencimento", "maturity_date", "d", "original maturity; null for perpetual/undated", "date"),
    ("Motivo de Saida", "exit_reason", "s", "'dd/mm/yyyy - REASON' of the exclusion", ""),
    ("Data de Saida / Novo Vencimento", "exit_or_new_maturity_date", "d", "exit date or renegotiated maturity", "date"),
    ("Data do Inicio da Rentabilidade", "accrual_start_date", "d", "start of remuneration", "date"),
    ("Data do Inicio da Distribuicao", "distribution_start_date", "d", "start of distribution", "date"),
    ("Data da Proxima Repactuacao", "next_repactuation_date", "d", "next repactuation (always - so far)", "date"),
    ("Ato Societario (1)", "corporate_act_1", "s", "AGE, RCA, AGO", ""),
    ("Data do Ato (1)", "corporate_act_1_date", "d", "date of the act", "date"),
    ("Ato Societario (2)", "corporate_act_2", "s", "second act", ""),
    ("Data do Ato (2)", "corporate_act_2_date", "d", "date of the second act", "date"),
    ("Forma", "form", "s", "Escritural or Nominativa", ""),
    ("Garantia/Especie", "guarantee", "s", "Quirografária, Real, Subordinada, Flutuante", ""),
    ("Classe", "class", "s", "Simples, Conversível, Permutável", ""),
    ("Quantidade Emitida", "qty_issued", "i", "debentures issued", "debentures"),
    ("Artigo 14", "qty_art14", "i", "quantity under CVM 476 art. 14 (supplementary lot)", "debentures"),
    ("Artigo 24", "qty_art24", "i", "quantity under art. 24 (additional lot)", "debentures"),
    ("Quantidade em Mercado", "qty_market", "i", "debentures outstanding", "debentures"),
    ("Quantidade em Tesouraria", "qty_treasury", "i", "debentures in treasury", "debentures"),
    ("Quantidade Resgatada", "qty_redeemed", "i", "redeemed", "debentures"),
    ("Quantidade  Cancelada", "qty_cancelled", "i", "cancelled", "debentures"),
    ("Quantidade Convertida no SND", "qty_converted_snd", "i", "converted in SND", "debentures"),
    ("Quantidade Convertida fora do SND", "qty_converted_out", "i", "converted outside SND", "debentures"),
    ("Quantidade Permutada no SND", "qty_exchanged_snd", "i", "exchanged in SND", "debentures"),
    ("Quantidade Permutada fora do SND", "qty_exchanged_out", "i", "exchanged outside SND", "debentures"),
    ("Unidade Monetaria", "issue_currency", "s", "currency of the nominal value at issue", ""),
    ("Valor Nominal na Emissao", "nominal_at_issue", "n", "nominal value at issue", "currency per debenture"),
    ("Unidade Monetaria", "current_currency", "s", "currency of the current nominal value", ""),
    (
        "Valor Nominal Atual",
        "nominal_current",
        "n",
        "current nominal value (after amortisations)",
        "currency per debenture",
    ),
    ("Data Ult. VNA", "nominal_updated_on", "d", "date of the last nominal-value update", "date"),
    ("indice", "indexer", "s", "index: DI, IPCA, IGP-M, TR, PRÉ, SEM-ÍNDICE...", ""),
    ("Tipo", "indexer_role", "s", "role of the index (Integrante de Juros, Correção Monetária)", ""),
    ("Criterio de Calculo", "calc_criterion", "s", "Padrão or Não Padrão - SND", ""),
    ("Dia de Referencia para indice de Precos", "price_index_ref_day", "i", "reference day of the price index", "day"),
    ("Criterio para indice", "index_day_count", "s", "DC calendar or DU business days", ""),
    ("Corrige a cada", "adjusts_every", "s", "always empty so far", ""),
    (
        "Percentual Multiplicador/Rentabilidade",
        "index_percent",
        "n",
        "percent of the index (point decimal)",
        "% of index",
    ),
    ("Limite da TJLP", "tjlp_limit", "n", "TJLP cap", "% a.a."),
    ("Tipo de Tratamento do Limite da TJLP", "tjlp_limit_treatment", "s", "Linear or Captalizado", ""),
    ("Juros Criterio Antigo do SND", "interest_old_rule", "s", "free text of the old interest rule", ""),
    ("Premios Criterio Antigo do SND", "premium_old_rule", "s", "free text of the old premium rule", ""),
    ("Amortizacao - Taxa", "amort_rate", "n", "amortisation rate per instalment (point decimal)", "%"),
    ("Amortizacao - Cada", "amort_every", "i", "instalment interval", "in `amort_unit`"),
    ("Amortizacao - Unidade", "amort_unit", "s", "MES, DIA", ""),
    ("Amortizacao - Carencia", "amort_grace_until", "d", "first amortisation date", "date"),
    ("Amortizacao - Criterio", "amort_day_rule", "s", "Útil or Civil", ""),
    ("Tipo de Amortizacao", "amort_type", "s", "amortisation type as written", ""),
    ("Juros Criterio Novo - Taxa", "coupon_rate", "n", "spread / coupon rate (comma decimal)", "% a.a."),
    ("Juros Criterio Novo - Prazo", "coupon_basis", "s", "day-count basis (252, 360, UTI...)", ""),
    ("Juros Criterio Novo - Cada", "coupon_every", "i", "coupon interval", "in `coupon_unit`"),
    ("Juros Criterio Novo - Unidade", "coupon_unit", "s", "MES, DIA", ""),
    ("Juros Criterio Novo - Carencia", "coupon_grace_until", "d", "first coupon date", "date"),
    ("Juros Criterio Novo - Criterio", "coupon_day_rule", "s", "Útil, Comercial...", ""),
    ("Juros Criterio Novo - Tipo", "coupon_compounding", "s", "Exponencial or Linear", ""),
    ("Premio Criterio Novo - Taxa", "premium_rate", "n", "premium rate", "%"),
    ("Premio Criterio Novo - Prazo", "premium_basis", "s", "premium day-count basis", ""),
    ("Premio Criterio Novo - Cada", "premium_every", "i", "premium interval", "in `premium_unit`"),
    ("Premio Criterio Novo - Unidade", "premium_unit", "s", "premium interval unit", ""),
    ("Premio Criterio Novo - Carencia", "premium_grace_until", "d", "first premium date", "date"),
    ("Premio Criterio Novo - Criterio", "premium_day_rule", "s", "premium day rule", ""),
    ("Premio Criterio Novo - Tipo", "premium_compounding", "s", "premium compounding", ""),
    ("Participacao - Taxa", "participation_rate", "n", "profit participation rate", "%"),
    ("Participacao - Cada", "participation_every", "i", "participation interval", "in `participation_unit`"),
    ("Participacao - Unidade", "participation_unit", "s", "participation interval unit", ""),
    ("Participacao - Carencia", "participation_grace_until", "d", "first participation date", "date"),
    ("Participacao - Descricao", "participation_description", "s", "what the participation is on", ""),
    ("Banco Mandatario", "paying_bank", "s", "mandated bank", ""),
    ("Agente Fiduciario", "trustee", "s", "trustee (company)", ""),
    ("Instituicao Depositaria", "depositary", "s", "depositary institution", ""),
    ("Coordenador Lider", "lead_coordinator", "s", "lead underwriter", ""),
    ("CNPJ", "issuer_cnpj", "s", "issuer CNPJ, 14 digits", ""),
    ("Deb. Incent. (Lei 12.431)", "incentivised", "s", "S/N: tax-incentivised (Lei 12.431)", ""),
    ("Escritura Padronizada", "standard_deed", "s", "n or empty", ""),
    ("Resgate Antecipado", "early_redemption", "s", "S/N/empty: early redemption clause", ""),
)
TERMS_HEADER = tuple(c[0] for c in TERMS_COLUMNS)
_DTYPE: dict[str, Any] = {"s": pl.String, "d": pl.Date, "i": pl.Int64, "n": DEC}

TERMS = Contract(
    table="staging.snd_debentures.caracteristicas",
    version=1,
    description="Terms of a debenture as SND publishes them (current snapshot; one row per debenture and issuer).",
    columns=tuple(
        Column(
            name, _DTYPE[kind], f"{src}: {meaning}", src.lower(), unit, nullable=name not in ("ticker", "issue_date")
        )
        for src, name, kind, meaning, unit in TERMS_COLUMNS
    ),
    rules=(
        Rule("cnpj_14_digits", pl.col("issuer_cnpj").is_null() | pl.col("issuer_cnpj").str.contains(r"^\d{14}$")),
        Rule("quantities_non_negative", pl.col("qty_issued").is_null() | (pl.col("qty_issued") >= 0)),
    ),
    key=("ticker", "issuer_cnpj", "raw_sha256"),
)

PRICES_HEADER = (
    "Data",
    "Emissor",
    "Código do Ativo",
    "ISIN",
    "Quantidade",
    "Número de Negócios",
    "PU Mínimo",
    "PU Médio",
    "PU Máximo",
    "% PU da Curva",
)

SECONDARY_PRICE = Contract(
    table="staging.snd_debentures.secondary_price",
    version=1,
    description="Secondary-market trade summary of one debenture on one day (SND 'Preços de Negociação').",
    columns=(
        Column("trade_date", pl.Date, "Data", "data", "date", False),
        Column("issuer_name", pl.String, "Emissor as written", "emissor"),
        Column("ticker", pl.String, "Código do Ativo", "código do ativo", "", False),
        Column("isin", pl.String, "ISIN as written", "ISIN"),
        Column("quantity", DEC, "Quantidade traded", "quantidade", "debentures"),
        Column(
            "n_trades", pl.Int64, "Número de Negócios; null when '-' (not published before 2010)", "negócios", "count"
        ),
        Column("pu_min_brl", DEC, "PU Mínimo of the day", "PU mínimo", "BRL per debenture"),
        Column("pu_avg_brl", DEC, "PU Médio of the day", "PU médio", "BRL per debenture"),
        Column("pu_max_brl", DEC, "PU Máximo of the day", "PU máximo", "BRL per debenture"),
        Column(
            "pct_of_curve_pu", DEC, "% PU da Curva: average PU over SND's curve PU; null on ND", "% PU da curva", "%"
        ),
    ),
    rules=(
        Rule("pu_ordered", pl.col("pu_min_brl").is_null() | (pl.col("pu_min_brl") <= pl.col("pu_max_brl"))),
        Rule("quantity_positive", pl.col("quantity").is_null() | (pl.col("quantity") > 0)),
    ),
    key=("ticker", "trade_date", "raw_sha256"),
)

CONTRACTS: dict[str, Contract] = {"caracteristicas": TERMS, "secondary_price": SECONDARY_PRICE}

_DATE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")


def _text(t: str) -> str | None:
    t = t.strip()
    return t or None


def _date(t: str) -> date | None:
    t = t.strip()
    if t in ("", "-"):
        return None
    if not _DATE.match(t):
        raise LayoutError(f"not a date: {t!r}")
    return datetime.strptime(t, "%d/%m/%Y").date()  # noqa: DTZ007 (a calendar date)


def _int(t: str) -> int | None:
    t = t.strip()
    if t in ("", "-"):
        return None
    if not t.isdigit():
        raise LayoutError(f"not an integer: {t!r}")
    return int(t)


def _dec(t: str) -> Decimal | None:
    """pt-BR number (`1.026,705058`), or a point-decimal one (`33.3333`); `-`, empty and ND are no value."""
    t = t.strip()
    if t in ("", "-", "ND"):
        return None
    s = t.replace(".", "").replace(",", ".") if "," in t else t
    try:
        d = Decimal(s)
    except InvalidOperation as e:
        raise LayoutError(f"not a number: {t!r}") from e
    exp = d.as_tuple().exponent
    if not d.is_finite() or (isinstance(exp, int) and exp < -12):
        raise LayoutError(f"unsupported number: {t!r}")
    return d


_CONVERT = {"s": _text, "d": _date, "i": _int, "n": _dec}


def _lines(blob: bytes) -> list[str]:
    return blob.decode("latin-1").replace("\r\n", "\n").split("\n")


def parse_terms(blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
    lines = _lines(blob)
    head = next((i for i, ln in enumerate(lines[:12]) if ln.startswith(TERMS_FIRST_COLUMN)), None)
    if head is None:
        raise NotData("not an SND terms file")
    cols = tuple(c.strip() for c in lines[head].split("\t"))
    if cols != TERMS_HEADER:
        raise LayoutError(f"columns changed: {len(cols)} vs {len(TERMS_HEADER)}; {set(cols) ^ set(TERMS_HEADER)}")
    names = [c[1] for c in TERMS_COLUMNS]
    conv = [_CONVERT[c[2]] for c in TERMS_COLUMNS]
    out: list[dict[str, Any]] = []
    for i, ln in enumerate(lines[head + 1 :], start=head + 2):
        if not ln.strip():
            continue
        f = ln.split("\t")
        if len(f) != len(cols):
            raise LayoutError(f"line {i}: {len(f)} fields, expected {len(cols)}")
        rec = {n: cv(v) for n, cv, v in zip(names, conv, f, strict=True)}
        rec["raw_locator"] = f"line={i}"
        out.append(rec)
    yield Parsed("caracteristicas", "all", _frame(out, TERMS, row))


def parse_prices(blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
    lines = _lines(blob)
    if not lines or not lines[0].startswith("Mercado Secundário de Debêntures"):
        raise NotData("not an SND secondary-market file")
    head = next((i for i, ln in enumerate(lines[:6]) if ln.startswith("Data\t")), None)
    if head is None:
        raise LayoutError("no header line")
    cols = tuple(c.strip() for c in lines[head].split("\t"))
    if cols != PRICES_HEADER:
        raise LayoutError(f"columns changed: {cols}")
    if any(NO_DATA in ln for ln in lines[head + 1 : head + 3]):
        return
    out: list[dict[str, Any]] = []
    for i, ln in enumerate(lines[head + 1 :], start=head + 2):
        if not ln.strip():
            continue
        f = ln.split("\t")
        if len(f) != len(cols):
            raise LayoutError(f"line {i}: {len(f)} fields, expected {len(cols)}")
        out.append(
            {
                "trade_date": _date(f[0]),
                "issuer_name": _text(f[1]),
                "ticker": _text(f[2]),
                "isin": _text(f[3]),
                "quantity": _dec(f[4]),
                "n_trades": _int(f[5]),
                "pu_min_brl": _dec(f[6]),
                "pu_avg_brl": _dec(f[7]),
                "pu_max_brl": _dec(f[8]),
                "pct_of_curve_pu": _dec(f[9]),
                "raw_locator": f"line={i}",
            }
        )
    df = _frame(out, SECONDARY_PRICE, row)
    df = df.with_columns(pl.col("trade_date").dt.year().alias("_year"))
    for (year,), part in df.partition_by("_year", as_dict=True, maintain_order=True).items():
        yield Parsed("secondary_price", f"year={year}", part.drop("_year"))


def _frame(rows: list[dict[str, Any]], contract: Contract, row: dict[str, Any]) -> pl.DataFrame:
    schema = {c.name: c.dtype for c in contract.columns} | {"raw_locator": pl.String}
    return pl.DataFrame(rows, schema=schema).with_columns(
        pl.lit(row["raw_sha256"]).alias("raw_sha256"), pl.lit(row["ingest_run_id"]).alias("ingest_run_id")
    )
