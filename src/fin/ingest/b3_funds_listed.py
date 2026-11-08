"""B3's listed-funds pages (docs/sources/b3_funds_listed.md): which funds B3 lists, under which acronym, and the
Fundos.NET documents of each ETF, the official route from a B3 acronym to a fund CNPJ.

`https://sistemaswebb3-listados.b3.com.br/fundsListedProxy/Search/<Endpoint>/<base64(JSON)>` (measured 2026-11-08,
browser UA, no login; the page `fundsListedPage` is an Angular app):
- `GetListFunds {language, typeFund, pageNumber, pageSize}`: (id = the fund's Fundos.NET id, acronym, fundName,
  tradingName). Types from the page's `assets/funds.json`: ETF, ETF-RF, ETF-FII, ETF-CRIPTO, FII, FIAGRO-FII… (134
  ETF on 2026-11-08). No CNPJ.
- `GetStructuredReports {language, dateInitial, dateFinal, pageNumber, pageSize, idFNET, typeFund, type}`: the fund's
  structured reports, each with `urlViewerFundosNet` (…visualizarDocumento?id=<doc id>). Type 64 = Informe Diário,
  whose XML names the CNPJ (`b3_fundosnet_daily`), so acronym -> idFNET -> doc id -> CNPJ.
- `GetDetailFund` / `GetListClassFund` answer an empty body for ETFs, in the browser too (BOVA, AGRI).

The list is current state only: archived daily (`ephemeral`). Staging `listed_fund` (one row per type and fund as
listed that day) and `fund_report` (one row per document of a report page).
"""

from __future__ import annotations

import base64
import json
import re
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from typing import Any, ClassVar
from zoneinfo import ZoneInfo

import polars as pl

from fin.config import Zones
from fin.ingest.base import Connector, Mode, Parsed
from fin.ingest.fetch import FetchSpec
from fin.ingest.http import BROWSER_UA
from fin.schema import Column, Contract

BASE = "https://sistemaswebb3-listados.b3.com.br/fundsListedProxy/Search"
PAGE = 120
TYPES = ("ETF", "ETF-RF", "ETF-FII", "ETF-CRIPTO", "FII", "FIAGRO-FII")
ETF_TYPES = frozenset({"ETF", "ETF-RF", "ETF-FII", "ETF-CRIPTO"})
DAILY_REPORT = 64  # Fundos.NET type "Informe Diário"
REPORT_DAYS = 365
BRT = ZoneInfo("America/Sao_Paulo")
DOC_ID = re.compile(r"[?&]id=(\d+)")

LISTED_FUND = Contract(
    table="staging.b3_funds_listed.listed_fund",
    version=1,
    description="A fund B3 lists on a given day: type, Fundos.NET id, acronym (ticker root) and names.",
    columns=(
        Column("snapshot_date", pl.Date, "the day the list was read (BRT)", "data da consulta", "date", nullable=False),
        Column("type_fund", pl.String, "typeFund asked (ETF, ETF-RF, FII…)", "tipo de fundo", nullable=False),
        Column("fnet_id", pl.Int64, "id: the fund's Fundos.NET id", "id Fundos.NET", nullable=False),
        Column("acronym", pl.String, "acronym: the ticker root", "sigla"),
        Column("fund_name", pl.String, "fundName as written", "nome do fundo"),
        Column("trading_name", pl.String, "tradingName as written", "nome de pregão"),
    ),
    key=("snapshot_date", "type_fund", "fnet_id"),
)
FUND_REPORT = Contract(
    table="staging.b3_funds_listed.fund_report",
    version=1,
    description="A Fundos.NET structured report B3 lists under a fund's Fundos.NET id.",
    columns=(
        Column("fnet_id", pl.Int64, "the fund's Fundos.NET id asked", "id Fundos.NET", nullable=False),
        Column("type_fund", pl.String, "typeFund asked", "tipo de fundo", nullable=False),
        Column(
            "doc_id", pl.Int64, "Fundos.NET document id (from urlViewerFundosNet)", "id do documento", nullable=False
        ),
        Column("report_type", pl.String, "describleType as written", "tipo de relatório"),
        Column("reference_date", pl.Date, "referenceDate", "data de referência", "date"),
        Column("delivered_at", pl.Datetime("us", "UTC"), "deliveryDateFormat (BRT) in UTC", "entrega", "timestamp"),
        Column("version", pl.Int32, "version", "versão"),
    ),
    key=("fnet_id", "doc_id"),
)
CONTRACTS = {"listed_fund": LISTED_FUND, "fund_report": FUND_REPORT}


def encode(params: dict[str, Any]) -> str:
    return base64.b64encode(json.dumps(params, separators=(",", ":"), ensure_ascii=False).encode()).decode()


def decode(url: str) -> dict[str, Any]:
    return dict(json.loads(base64.b64decode(url.rsplit("/", 1)[1])))


def _frame(rows: list[dict[str, Any]], contract: Contract, row: dict[str, Any]) -> pl.DataFrame:
    schema = {c.name: c.dtype for c in contract.columns} | {"raw_locator": pl.String}
    return pl.DataFrame(rows, schema=schema, orient="row").with_columns(
        pl.lit(row["raw_sha256"]).alias("raw_sha256"), pl.lit(row["ingest_run_id"]).alias("ingest_run_id")
    )


def parse_payload(blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
    doc = json.loads(blob)
    params = json.loads(row["request"])
    p = decode(params["url"])
    if row["dataset_id"] == "fund_list":
        snap = datetime.fromisoformat(str(row["fetched_at"])).astimezone(BRT).date()
        rows = [
            {
                "snapshot_date": snap, "type_fund": p["typeFund"], "fnet_id": int(r["id"]),
                "acronym": (r.get("acronym") or "").strip() or None, "fund_name": r.get("fundName"),
                "trading_name": (r.get("tradingName") or "").strip() or None, "raw_locator": f"$.results[{i}]",
            }
            for i, r in enumerate(doc.get("results") or [])
        ]  # fmt: skip
        yield Parsed("listed_fund", "all", _frame(rows, LISTED_FUND, row))
    elif row["dataset_id"] == "fund_reports":
        rows = []
        for i, r in enumerate(doc.get("results") or []):
            m = DOC_ID.search(r.get("urlViewerFundosNet") or "")
            if not m:
                continue
            at = datetime.strptime(r["deliveryDateFormat"], "%d/%m/%Y %H:%M").replace(tzinfo=BRT)
            rows.append({
                "fnet_id": int(p["idFNET"]), "type_fund": p["typeFund"], "doc_id": int(m.group(1)),
                "report_type": r.get("describleType"), "reference_date": date.fromisoformat(r["referenceDate"][:10]),
                "delivered_at": at, "version": r.get("version"), "raw_locator": f"$.results[{i}]",
            })  # fmt: skip
        yield Parsed("fund_report", "all", _frame(rows, FUND_REPORT, row))


class B3FundsListed(Connector):
    """B3's listed funds (ETF, ETF-RF, ETF-FII, ETF-CRIPTO, FII, Fiagro) and, for each ETF, its latest daily-report
    page: the documents tie the B3 acronym to the fund CNPJ (ADR-0029)."""

    source_id: ClassVar[str] = "b3_funds_listed"
    version: ClassVar[str] = "1"
    user_agent: ClassVar[str | None] = BROWSER_UA
    contracts: ClassVar[dict[str, Any]] = CONTRACTS
    dedup_staging: ClassVar[bool] = True

    def _spec(self, endpoint: str, params: dict[str, Any], dataset: str, locator: str) -> FetchSpec:
        from fin.ingest.snapshots import today_brt

        return FetchSpec(
            self.source_id,
            dataset,
            f"{BASE}/{endpoint}/{encode({'language': 'pt-br', **params})}",
            "json",
            reference_date=today_brt(),
            conditional=False,
            min_bytes=2,
            locator=locator,
        )

    def _list(self, type_fund: str, page: int) -> FetchSpec:
        params = {"typeFund": type_fund, "pageNumber": page, "pageSize": PAGE}
        return self._spec("GetListFunds", params, "fund_list", f"{type_fund};page={page}")

    def discover(self, mode: Mode, zones: Zones, **options: Any) -> Iterable[FetchSpec]:
        for t in TYPES:
            yield self._list(t, 1)

    def follow(self, spec: FetchSpec, blob: bytes) -> Iterable[FetchSpec]:
        from fin.ingest.snapshots import today_brt

        if spec.dataset_id != "fund_list":
            return []
        doc = json.loads(blob)
        p = decode(spec.url)
        out: list[FetchSpec] = []
        if int(p["pageNumber"]) == 1:
            pages = int((doc.get("page") or {}).get("totalPages") or 1)
            out += [self._list(p["typeFund"], k) for k in range(2, pages + 1)]
        if p["typeFund"] in ETF_TYPES:
            today = today_brt()
            for r in doc.get("results") or []:
                params = {
                    "dateInitial": (today - timedelta(days=REPORT_DAYS)).isoformat(), "dateFinal": today.isoformat(),
                    "pageNumber": 1, "pageSize": 20, "idFNET": str(r["id"]), "typeFund": p["typeFund"],
                    "type": DAILY_REPORT,
                }  # fmt: skip
                out.append(self._spec("GetStructuredReports", params, "fund_reports", f"{p['typeFund']};{r['id']}"))
        return out

    def parse(self, blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
        return parse_payload(blob, row)

    def derive(self, zones: Zones, run: Any) -> None:
        from fin.core import etfs

        etfs.build(zones, run)
