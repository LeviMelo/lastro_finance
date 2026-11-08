"""B3 Fundos.NET 'Informe Diário' of ETFs -> staging `daily` and `listing` (docs/sources/b3_fundosnet_daily.md).

ETFs (CVM type FIIM) deliver their daily report through Fundos.NET, not CVM's open data, whose INF_DIARIO stops
holding them in 2018-09 (BOVA11: last row 2018-09-06). One XML per fund and business day, 225,340 documents from
2018-06-29 (category 6, type 64; measured 2026-11-08). Layouts measured on documents of 2018, 2022, 2024 and 2026:
- root `DOC_ARQ`, with namespace `urn:infdiario` (2022-) or none (2018); declared UTF-8 or Windows-1252;
- `CAB_INFORM/DT_COMPT` dd/mm/yyyy is the NAV date; 2018 documents carry `CNPJ_FDO` in the header and the day again
  as `INFORM/DIA_COMPT`; later ones carry `CNPJ_FDO` in each `INFORM`;
- values with a decimal comma: VL_QUOTA (12 decimals), PATRIM_LIQ, VL_TOTAL, CAPTC_DIA, RESG_DIA, NR_COTST.
`LISTA_COTST_SIGNIF` (holders of a significant share, with CPF or CNPJ) is personal data and is not parsed.
"""

from __future__ import annotations

import dataclasses
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from typing import Any

import polars as pl

from fin.ingest import fundosnet
from fin.ingest.base import Parsed
from fin.schema import Column, Contract, Rule

QUOTA = pl.Decimal(38, 12)
MONEY = pl.Decimal(38, 4)
NUMBER = re.compile(r"^-?\d+(?:,\d+)?$")


class LayoutError(ValueError):
    pass


DAILY = Contract(
    table="staging.b3_fundosnet_daily.daily",
    version=2,
    description="An ETF's daily report: NAV per quota, net assets, flows and holders, as delivered to Fundos.NET.",
    columns=(
        Column("doc_id", pl.Int64, "Fundos.NET document id", "id do documento", nullable=False),
        Column("fund_cnpj", pl.String, "CNPJ_FDO, 14 digits (the class CNPJ since CVM 175)", "CNPJ", nullable=False),
        Column("reference_date", pl.Date, "DT_COMPT: the NAV date", "data de competência", "date", nullable=False),
        Column("quota_value_brl", QUOTA, "VL_QUOTA: NAV per quota", "valor da cota", "BRL per quota"),
        Column("net_assets_brl", MONEY, "PATRIM_LIQ", "patrimônio líquido", "BRL"),
        Column("portfolio_value_brl", MONEY, "VL_TOTAL: total portfolio value", "valor total da carteira", "BRL"),
        Column("subscriptions_brl", MONEY, "CAPTC_DIA", "captação do dia", "BRL"),
        Column("redemptions_brl", MONEY, "RESG_DIA", "resgate do dia", "BRL"),
        Column("holders", pl.Int64, "NR_COTST", "número de cotistas", "count"),
        Column("next_nav_date", pl.Date, "DATA_PROX_PL: date of the next NAV", "data do próximo PL", "date"),
    ),
    rules=(
        Rule("cnpj_14_digits", pl.col("fund_cnpj").str.contains(r"^\d{14}$")),
        # a quota of 0 is "no NAV that day" as some funds file it (1,093 rows, 2018-2020): kept as published,
        # skipped wherever a price is needed (core etf_nav: quota > 0); quarantining it hid real reports
        Rule("quota_non_negative", pl.col("quota_value_brl").is_null() | (pl.col("quota_value_brl") >= 0)),
    ),
    key=("doc_id", "fund_cnpj", "reference_date"),
)
LISTING = dataclasses.replace(fundosnet.LISTING, table="staging.b3_fundosnet_daily.listing")
CONTRACTS = {"daily": DAILY, "listing": LISTING}


def _local(tag: str) -> str:
    return tag.rpartition("}")[2]


def _children(el: ET.Element) -> dict[str, str]:
    return {_local(c.tag): (c.text or "").strip() for c in el if (c.text or "").strip()}


def _day(text: str | None) -> date | None:
    if not text:
        return None
    d, m, y = text.split("/")
    return date(int(y), int(m), int(d))


def _num(text: str | None, scale: int, field: str) -> Decimal | None:
    if not text:
        return None
    if not NUMBER.match(text):
        raise LayoutError(f"Informe Diário: {field}={text!r}")
    if len(text.partition(",")[2]) > scale:  # never round silently
        raise LayoutError(f"Informe Diário: {field}={text!r} has more than {scale} decimals")
    return Decimal(text.replace(",", "."))


def parse_daily(blob: bytes, row: dict[str, Any]) -> pl.DataFrame:
    root = ET.fromstring(blob)
    if _local(root.tag) != "DOC_ARQ":
        raise LayoutError(f"Informe Diário: root {root.tag}")
    head = next((c for c in root if _local(c.tag) == "CAB_INFORM"), None)
    lst = next((c for c in root if _local(c.tag) == "LISTA_INFORM"), None)
    if head is None or lst is None:
        raise LayoutError("Informe Diário: no CAB_INFORM or LISTA_INFORM")
    h = _children(head)
    ref = _day(h.get("DT_COMPT"))
    if ref is None:
        raise LayoutError("Informe Diário: no DT_COMPT")
    doc_id = fundosnet.doc_id_of(row)
    out: list[dict[str, Any]] = []
    for i, inf in enumerate(c for c in lst if _local(c.tag) == "INFORM"):
        f = _children(inf)
        if "DIA_COMPT" in f and int(f["DIA_COMPT"]) != ref.day:
            raise LayoutError(f"Informe Diário: DIA_COMPT {f['DIA_COMPT']} vs DT_COMPT {ref}")
        holders = f.get("NR_COTST")
        out.append({
            # some administrators write the CNPJ formatted (38.350.645/0001-27: 2,923 rows had been quarantined)
            "doc_id": doc_id, "fund_cnpj": re.sub(r"\D", "", f.get("CNPJ_FDO") or h.get("CNPJ_FDO") or "") or None,
            "reference_date": ref,
            "quota_value_brl": _num(f.get("VL_QUOTA"), 12, "VL_QUOTA"),
            "net_assets_brl": _num(f.get("PATRIM_LIQ"), 4, "PATRIM_LIQ"),
            "portfolio_value_brl": _num(f.get("VL_TOTAL"), 4, "VL_TOTAL"),
            "subscriptions_brl": _num(f.get("CAPTC_DIA"), 4, "CAPTC_DIA"),
            "redemptions_brl": _num(f.get("RESG_DIA"), 4, "RESG_DIA"),
            "holders": int(holders) if holders else None, "next_nav_date": _day(f.get("DATA_PROX_PL")),
            "raw_locator": f"LISTA_INFORM/INFORM[{i}]",
        })  # fmt: skip
    if not out:
        raise LayoutError("Informe Diário: no INFORM")
    schema = {c.name: c.dtype for c in DAILY.columns} | {"raw_locator": pl.String}
    return pl.DataFrame(out, schema=schema, orient="row").with_columns(
        pl.lit(row["raw_sha256"]).alias("raw_sha256"), pl.lit(row["ingest_run_id"]).alias("ingest_run_id")
    )


def parse_payload(blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
    ds = str(row["dataset_id"])
    if ds == "informe_diario":
        yield Parsed("daily", f"id_block={fundosnet.doc_id_of(row) // 100_000}", parse_daily(blob, row))
    elif ds == "listagem":
        yield Parsed("listing", "all", fundosnet.parse_listing(blob, row))
    else:
        raise LayoutError(f"Informe Diário: dataset {ds}")
