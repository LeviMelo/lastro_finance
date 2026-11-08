"""B3 Fundos.NET distribution notices -> staging `distribution` and `listing` (docs/sources/b3_fundosnet.md).

- `distribution`: one row per (notice, Provento, kind). A Provento may carry a `Rendimento` (income, with its tax
  exemption flag) and an `Amortizacao` (capital return, `tipo` Parcial/Total); 430 of 19,299 carry both.
  Values are exact decimals in BRL per quota as written. Contact person and phone (`ResponsavelInformacao`,
  `TelefoneContato`) are personal data and are not parsed.
- `listing`: one row per document in a listing page, with `dataEntrega`, the minute B3 received the notice: the
  knowledge time of the distribution (PLAN §4.1 invariant 3), and `versao` (re-filings).

Layout measured on 16,685 notices (2016-11-30 → 2026-11-06): every date ISO, every value `\\d+(\\.\\d+)?`; one
notice holds an `InformeMensal` instead of distributions and is counted as not data.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import polars as pl

from fin.ingest.base import NotData, Parsed
from fin.schema import Column, Contract, Rule

BRT = ZoneInfo("America/Sao_Paulo")
VALUE = pl.Decimal(38, 22)  # measured: up to 19 decimals (1 notice) and 7 integer digits (2026-11-08)
KT = pl.Datetime("us", "UTC")
KINDS = ("rendimento", "amortizacao")


class LayoutError(ValueError):
    pass


DISTRIBUTION = Contract(
    table="staging.b3_fundosnet.distribution",
    version=2,
    description="A fund's announced distribution per quota, from a structured 'Rendimentos e Amortizações' notice.",
    columns=(
        Column("doc_id", pl.Int64, "Fundos.NET document id", "id do documento", nullable=False),
        Column("fund_name", pl.String, "NomeFundo as written", "nome do fundo", nullable=False),
        Column("fund_cnpj", pl.String, "CNPJFundo, 14 digits", "CNPJ do fundo", nullable=False),
        Column("admin_cnpj", pl.String, "CNPJAdministrador, 14 digits", "CNPJ do administrador"),
        Column("info_date", pl.Date, "DataInformacao", "data da informação", "date"),
        Column("isin", pl.String, "CodISIN of the quota", "ISIN", nullable=False),
        Column(
            "trading_code",
            pl.String,
            "CodNegociacao as written (a ticker or a B3 internal code); absent for unlisted quotas",
            "código de negociação",
        ),
        Column("kind", pl.String, "rendimento (income) or amortizacao (capital return)", "tipo", nullable=False),
        Column("amortization_type", pl.String, "Amortizacao/@tipo: Parcial or Total", "tipo de amortização"),
        Column("approval_text", pl.String, "AtoSocietarioAprovacao as written", "ato societário de aprovação"),
        Column("base_date", pl.Date, "DataBase: the data-com", "data-base (data com)", "date", nullable=False),
        Column("payment_date", pl.Date, "DataPagamento", "data de pagamento", "date", nullable=False),
        Column("value_per_quota", VALUE, "ValorProvento", "valor por cota", "BRL per quota", nullable=False),
        Column(
            "reference_period", pl.String, "PeriodoReferencia as written (e.g. Novembro-2025)", "período de referência"
        ),
        Column("tax_exempt", pl.Boolean, "RendimentoIsentoIR (income only): Sim/Não", "isento de IR"),
    ),
    rules=(
        Rule("kind_known", pl.col("kind").is_in(KINDS)),
        Rule("value_non_negative", pl.col("value_per_quota") >= 0),
        Rule("cnpj_14_digits", pl.col("fund_cnpj").str.contains(r"^\d{14}$")),
        # a malformed ISIN ("0", "-", "TGARCTF009") or a payment dated before the data-com (a year typo: base
        # 2020-12-30, paid 2020-01-15) is the source's: the payout is kept as written and reported by the quality
        # check `fii_payout_suspect`; core maps a malformed ISIN through the trading code (2026-11-08: 108 and 214
        # rows had been quarantined, losing real payouts)
    ),
    key=("doc_id", "isin", "trading_code", "kind"),
)

LISTING = Contract(
    table="staging.b3_fundosnet.listing",
    version=1,
    description="One document as a Fundos.NET listing page served it: delivery minute, version and status.",
    columns=(
        Column("doc_id", pl.Int64, "Fundos.NET document id", "id do documento", nullable=False),
        Column(
            "delivered_at",
            KT,
            "dataEntrega (minute, Brasília time) in UTC",
            "data de entrega",
            "timestamp",
            nullable=False,
        ),
        Column("reference_text", pl.String, "dataReferencia as written", "data de referência"),
        Column("fund_description", pl.String, "descricaoFundo", "descrição do fundo"),
        Column("trading_name", pl.String, "nomePregao (e.g. 'FII TINF')", "nome de pregão"),
        Column(
            "version", pl.Int32, "versao: 1 for the first filing, +1 per re-filing", "versão", "count", nullable=False
        ),
        Column("status", pl.String, "status code (AC…)", "status"),
        Column("status_text", pl.String, "descricaoStatus", "descrição do status"),
        Column("situation", pl.String, "situacaoDocumento (A…)", "situação do documento"),
        Column("modality", pl.String, "descricaoModalidade (Apresentação, Reapresentação…)", "modalidade"),
    ),
    key=("doc_id", "raw_sha256"),
)

CONTRACTS = {"distribution": DISTRIBUTION, "listing": LISTING}


def doc_id_of(row: dict[str, Any]) -> int:
    req = json.loads(row["request"])
    return int((req.get("params") or {})["id"])


def _text(el: ET.Element | None, tag: str) -> str | None:
    if el is None:
        return None
    found = el.find(tag)
    if found is None or found.text is None or not found.text.strip():
        return None
    return found.text.strip()


def _decimals(text: str | None) -> int:
    return len(text.partition(".")[2]) if text else 0


def _day(text: str | None) -> date | None:
    return date.fromisoformat(text) if text else None


def parse_distribution(blob: bytes, row: dict[str, Any]) -> pl.DataFrame:
    root = ET.fromstring(blob)
    if root.tag != "DadosEconomicoFinanceiros":
        raise LayoutError(f"Fundos.NET: root {root.tag}")
    informe = root.find("InformeRendimentos")
    if informe is None:
        kinds = [c.tag for c in root if c.tag != "DadosGerais"]
        raise NotData(f"Fundos.NET notice without InformeRendimentos (holds {kinds})")
    g = root.find("DadosGerais")
    doc_id = doc_id_of(row)
    common = {
        "doc_id": doc_id,
        "fund_name": _text(g, "NomeFundo"),
        "fund_cnpj": re.sub(r"\D", "", _text(g, "CNPJFundo") or "") or None,  # 27 notices write it formatted
        "admin_cnpj": _text(g, "CNPJAdministrador"),
        "info_date": _day(_text(g, "DataInformacao")),
    }
    out: list[dict[str, Any]] = []
    # two layouts (measured on all 36,384 notices, 2026-11-08): from 2022, one <Provento> per class with its own
    # CodISIN/CodNegociacao and ValorProvento (20,415); before, Rendimento/Amortizacao directly under
    # InformeRendimentos, the ISIN in DadosGerais (CodISINCota) and the value in ValorProventoCota (15,969)
    provs = informe.findall("Provento")
    blocks = (
        [(f"InformeRendimentos/Provento[{i}]", p, _text(p, "CodISIN"), _text(p, "CodNegociacao"))
         for i, p in enumerate(provs, start=1)]
        if provs
        else [("InformeRendimentos", informe, _text(g, "CodISINCota"), _text(g, "CodNegociacaoCota"))]
    )  # fmt: skip
    for where, prov, isin, code in blocks:
        for tag, kind in (("Rendimento", "rendimento"), ("Amortizacao", "amortizacao")):
            el = prov.find(tag)
            if el is None or len(el) == 0:  # an empty <Rendimento/> declares nothing
                continue
            exempt = _text(el, "RendimentoIsentoIR")
            out.append(
                common
                | {
                    "isin": isin,
                    "trading_code": code,
                    "kind": kind,
                    "amortization_type": el.get("tipo"),
                    "approval_text": _text(el, "AtoSocietarioAprovacao") or _text(el, "DataAprovacao"),
                    "base_date": _day(_text(el, "DataBase")),
                    "payment_date": _day(_text(el, "DataPagamento")),
                    "value_per_quota": _text(el, "ValorProvento") or _text(el, "ValorProventoCota"),
                    "reference_period": _text(el, "PeriodoReferencia"),
                    "tax_exempt": None if exempt is None else {"Sim": True, "Não": False}.get(exempt),
                    "raw_locator": f"{where}/{tag}",
                }
            )
    too_fine = [r["value_per_quota"] for r in out if _decimals(r["value_per_quota"]) > VALUE.scale]
    if too_fine:  # a cast would round silently
        raise LayoutError(f"Fundos.NET: value with more than {VALUE.scale} decimals: {too_fine[0]}")
    schema = {c.name: c.dtype for c in DISTRIBUTION.columns} | {"value_per_quota": pl.String, "raw_locator": pl.String}
    df = pl.DataFrame(out, schema=schema, orient="row")
    return df.with_columns(
        pl.col("value_per_quota").cast(VALUE),
        pl.lit(row["raw_sha256"]).alias("raw_sha256"),
        pl.lit(row["ingest_run_id"]).alias("ingest_run_id"),
    )


def parse_listing(blob: bytes, row: dict[str, Any]) -> pl.DataFrame:
    page = json.loads(blob)
    out: list[dict[str, Any]] = []
    for i, d in enumerate(page["data"]):
        at = datetime.strptime(d["dataEntrega"], "%d/%m/%Y %H:%M").replace(tzinfo=BRT)
        out.append(
            {
                "doc_id": int(d["id"]),
                "delivered_at": at,
                "reference_text": d.get("dataReferencia"),
                "fund_description": d.get("descricaoFundo"),
                "trading_name": d.get("nomePregao"),
                "version": int(d["versao"]),
                "status": d.get("status"),
                "status_text": d.get("descricaoStatus"),
                "situation": d.get("situacaoDocumento"),
                "modality": d.get("descricaoModalidade"),
                "raw_locator": f"$.data[{i}]",
            }
        )
    schema = {c.name: c.dtype for c in LISTING.columns} | {"raw_locator": pl.String}
    return pl.DataFrame(out, schema=schema, orient="row").with_columns(
        pl.lit(row["raw_sha256"]).alias("raw_sha256"), pl.lit(row["ingest_run_id"]).alias("ingest_run_id")
    )


def parse_payload(blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
    ds = str(row["dataset_id"])
    if ds == "informe_rendimentos":
        yield Parsed("distribution", f"id_block={doc_id_of(row) // 100_000}", parse_distribution(blob, row))
    elif ds == "listagem":
        yield Parsed("listing", "all", parse_listing(blob, row))
