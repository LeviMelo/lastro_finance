"""B3 listed-companies backend: issuers, cash distributions and stock events
(tier U; docs/sources/b3_company_events.md).

Requests are `GET <BASE>/<Endpoint>/<base64(compact JSON params)>`, always with `"language": "pt-br"` (other
languages change the number format). Three request shapes:
- `GetInitialCompanies` pages (120 issuers each): the issuer list, followed by
- `GetListedSupplementCompany` per issuer root: current stock events (with ISIN and factor), the current window of
  cash announcements (with ISIN and payment date) and share counts. A current-state view: archived at every refresh.
- `GetListedCashDividends` per trading name, paged: the full cash history (data-com, value per share, kind).

Universe: issuers whose 4-letter root traded in COTAHIST's spot market with a modern ticker (`XXXX3`…). Each issuer is
refreshed when its last fetch is `EVERY_DAYS` old, so the daily job spreads the load over the week.

Staging (source-shaped):
- `issuer`: one row per issuer of the list.
- `cash_event`: one row per cash history row; `value_cash` is per `quoted_per_shares` shares as B3 writes it.
- `stock_event` and `cash_announcement`: the Supplement's arrays.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Iterable
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction
from typing import Any, ClassVar

import polars as pl

from fin.config import Zones
from fin.ingest.base import Connector, Mode, Parsed
from fin.ingest.fetch import FetchSpec
from fin.ingest.http import BROWSER_UA
from fin.ingest.snapshots import held_rows, today_brt
from fin.schema import Column, Contract, Rule

BASE = "https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/CompanyCall"
PAGE = 120  # 200 returns an empty page (measured)
EVERY_DAYS = 7
DEC = pl.Decimal(38, 18)


def encode(params: dict[str, Any]) -> str:
    return base64.b64encode(json.dumps(params, separators=(",", ":"), ensure_ascii=False).encode()).decode()


def decode(url: str) -> dict[str, Any]:
    return dict(json.loads(base64.b64decode(url.rsplit("/", 1)[1])))


def _ptbr(text: str | None) -> str | None:
    """'1.234,56' -> '1234.56'; None and '' stay None."""
    if text is None or not str(text).strip():
        return None
    return str(text).strip().replace(".", "").replace(",", ".")


def _dmy(text: str | None) -> date | None:
    if not text or text.startswith("31/12/9999"):
        return None
    d, m, y = text[:10].split("/")
    return date(int(y), int(m), int(d))


_ROW = {"raw_sha256": pl.String, "raw_locator": pl.String, "ingest_run_id": pl.String}

ISSUER = Contract(
    table="staging.b3_company_events.issuer",
    version=1,
    description="An issuer of B3's listed-companies list.",
    columns=(
        Column("code_cvm", pl.String, "codeCVM", "código CVM", nullable=False),
        Column("root", pl.String, "issuingCompany: 4-letter ticker root", "raiz do código", nullable=False),
        Column("company_name", pl.String, "companyName", "razão social"),
        Column(
            "trading_name", pl.String, "tradingName: key of the cash history; changes with renames", "nome de pregão"
        ),
        Column("cnpj", pl.String, "cnpj as written (leading zeros may be lost)", "CNPJ"),
        Column("status", pl.String, "status (A…)", "situação"),
        Column("segment", pl.String, "segment", "segmento"),
        Column("listed_on", pl.Date, "dateListing; null for 31/12/9999", "data de listagem", "date"),
    ),
    key=("code_cvm", "raw_sha256"),
)

CASH_EVENT = Contract(
    table="staging.b3_company_events.cash_event",
    version=1,
    description="One row of an issuer's cash distribution history (dividends, JCP, rendimentos).",
    columns=(
        Column("root", pl.String, "issuer root the request was made for", "raiz", nullable=False),
        Column("trading_name", pl.String, "tradingName of the request", "nome de pregão", nullable=False),
        Column("type_stock", pl.String, "share class (ON, PN, PNA…, UNT)", "espécie", nullable=False),
        Column(
            "kind",
            pl.String,
            "corporateAction as written (DIVIDENDO, JRS CAP PROPRIO, RENDIMENTO…)",
            "provento",
            nullable=False,
        ),
        Column("approved_on", pl.Date, "dateApproval", "data de aprovação", "date"),
        Column("last_date_prior", pl.Date, "lastDatePriorEx: the data-com", "data com", "date", nullable=False),
        Column(
            "value_cash",
            DEC,
            "valueCash, per `quoted_per_shares` shares",
            "valor",
            "BRL per quoted_per_shares shares",
            nullable=False,
        ),
        Column(
            "quoted_per_shares",
            pl.Int64,
            "quotedPerShares (1, or 1000 for old per-thousand quotes)",
            "cotação por",
            "shares",
            nullable=False,
        ),
        Column("ratio", pl.String, "ratio as written", "razão"),
        Column("close_prior_ex", DEC, "closingPricePriorExDate", "fechamento antes do ex", "BRL per quoted_per_shares"),
        Column("close_prior_ex_on", pl.Date, "dateClosingPricePriorExDate", "data do fechamento", "date"),
    ),
    rules=(Rule("value_non_negative", pl.col("value_cash") >= 0),),
)

STOCK_EVENT = Contract(
    table="staging.b3_company_events.stock_event",
    version=1,
    description="A stock event (bonificação, desdobramento, grupamento…) as the issuer Supplement serves it.",
    columns=(
        Column("root", pl.String, "issuer root", "raiz", nullable=False),
        Column("isin", pl.String, "isinCode: the class that receives", "ISIN", nullable=False),
        Column("asset_issued", pl.String, "assetIssued: the class issued", "ativo emitido"),
        Column("label", pl.String, "label as written", "evento", nullable=False),
        Column(
            "factor",
            DEC,
            "factor as written; its unit depends on the label (source note §3)",
            "fator",
            "label-dependent",
            nullable=False,
        ),
        Column("approved_on", pl.Date, "approvedOn", "aprovação", "date"),
        Column("last_date_prior", pl.Date, "lastDatePrior: the data-com", "data com", "date"),
        Column("remarks", pl.String, "remarks", "observações"),
    ),
)

CASH_ANNOUNCEMENT = Contract(
    table="staging.b3_company_events.cash_announcement",
    version=1,
    description="A cash announcement of the Supplement's current window: has ISIN and payment date.",
    columns=(
        Column("root", pl.String, "issuer root", "raiz", nullable=False),
        Column("isin", pl.String, "isinCode", "ISIN", nullable=False),
        Column("label", pl.String, "label (DIVIDENDO, JRS CAP PROPRIO…)", "provento", nullable=False),
        Column("rate", DEC, "rate per share", "valor por ação", "BRL per share", nullable=False),
        Column("related_to", pl.String, "relatedTo (Anual/2025, Mensal/2026…)", "referente a"),
        Column("approved_on", pl.Date, "approvedOn", "aprovação", "date"),
        Column("last_date_prior", pl.Date, "lastDatePrior: the data-com", "data com", "date"),
        Column("payment_date", pl.Date, "paymentDate; null for 31/12/9999 (not yet set)", "pagamento", "date"),
    ),
)

SUBSCRIPTION = Contract(
    table="staging.b3_company_events.subscription",
    version=1,
    description="A rights offering (subscrição) as the issuer Supplement serves it.",
    columns=(
        Column("root", pl.String, "issuer root", "raiz", nullable=False),
        Column("isin", pl.String, "isinCode: the class with the right", "ISIN", nullable=False),
        Column("asset_issued", pl.String, "assetIssued", "ativo emitido"),
        Column("percentage", DEC, "new shares per 100 held", "percentual", "% of shares held", nullable=False),
        Column(
            "price_unit", DEC, "subscription price per share", "preço de subscrição", "BRL per share", nullable=False
        ),
        Column("trading_period", pl.String, "tradingPeriod as written", "período de negociação"),
        Column("subscription_date", pl.Date, "subscriptionDate", "data de subscrição", "date"),
        Column("approved_on", pl.Date, "approvedOn", "aprovação", "date"),
        Column("last_date_prior", pl.Date, "lastDatePrior: the data-com", "data com", "date"),
    ),
)

CONTRACTS = {
    "subscription": SUBSCRIPTION,
    "issuer": ISSUER,
    "cash_event": CASH_EVENT,
    "stock_event": STOCK_EVENT,
    "cash_announcement": CASH_ANNOUNCEMENT,
}


def _frame(
    rows: list[dict[str, Any]], contract: Contract, row: dict[str, Any], decimals: tuple[str, ...]
) -> pl.DataFrame:
    schema = {c.name: (pl.String if c.name in decimals else c.dtype) for c in contract.columns} | {
        "raw_locator": pl.String
    }
    df = pl.DataFrame(rows, schema=schema, orient="row")
    return df.with_columns(
        *[pl.col(c).cast(DEC) for c in decimals],
        pl.lit(row["raw_sha256"]).alias("raw_sha256"),
        pl.lit(row["ingest_run_id"]).alias("ingest_run_id"),
    )


def parse_issuers(blob: bytes, row: dict[str, Any]) -> pl.DataFrame:
    out = [
        {
            "code_cvm": r["codeCVM"],
            "root": r["issuingCompany"],
            "company_name": r.get("companyName"),
            "trading_name": r.get("tradingName"),
            "cnpj": r.get("cnpj"),
            "status": r.get("status"),
            "segment": r.get("segment"),
            "listed_on": _dmy(r.get("dateListing")),
            "raw_locator": f"$.results[{i}]",
        }
        for i, r in enumerate(json.loads(blob)["results"])
    ]
    return _frame(out, ISSUER, row, ())


def parse_cash(blob: bytes, row: dict[str, Any]) -> pl.DataFrame:
    params = decode(json.loads(row["request"])["url"])
    root = (row.get("notes") or "").split("|")[0]
    out = [
        {
            "root": root,
            "trading_name": params["tradingName"],
            "type_stock": r["typeStock"],
            "kind": r["corporateAction"],
            "approved_on": _dmy(r.get("dateApproval")),
            "last_date_prior": _dmy(r.get("lastDatePriorEx")),
            "value_cash": _ptbr(r.get("valueCash")),
            "quoted_per_shares": int(r.get("quotedPerShares") or 1),
            "ratio": r.get("ratio"),
            "close_prior_ex": _ptbr(r.get("closingPricePriorExDate")),
            "close_prior_ex_on": _dmy(r.get("dateClosingPricePriorExDate")),
            "raw_locator": f"$.results[{i}]",
        }
        for i, r in enumerate(json.loads(blob)["results"])
    ]
    return _frame(out, CASH_EVENT, row, ("value_cash", "close_prior_ex"))


def parse_supplement(blob: bytes, row: dict[str, Any]) -> tuple[pl.DataFrame, pl.DataFrame]:
    doc = json.loads(blob)
    sup = doc[0] if doc else {}
    root = (row.get("notes") or "").split("|")[0]
    stock = [
        {
            "root": root,
            "isin": s["isinCode"],
            "asset_issued": s.get("assetIssued"),
            "label": s["label"],
            "factor": _ptbr(s.get("factor")),
            "approved_on": _dmy(s.get("approvedOn")),
            "last_date_prior": _dmy(s.get("lastDatePrior")),
            "remarks": s.get("remarks") or None,
            "raw_locator": f"$[0].stockDividends[{i}]",
        }
        for i, s in enumerate(sup.get("stockDividends") or [])
    ]
    cash = [
        {
            "root": root,
            "isin": c["isinCode"],
            "label": c["label"],
            "rate": _ptbr(c.get("rate")),
            "related_to": c.get("relatedTo"),
            "approved_on": _dmy(c.get("approvedOn")),
            "last_date_prior": _dmy(c.get("lastDatePrior")),
            "payment_date": _dmy(c.get("paymentDate")),
            "raw_locator": f"$[0].cashDividends[{i}]",
        }
        for i, c in enumerate(sup.get("cashDividends") or [])
    ]
    return _frame(stock, STOCK_EVENT, row, ("factor",)), _frame(cash, CASH_ANNOUNCEMENT, row, ("rate",))


def parse_subscriptions(blob: bytes, row: dict[str, Any]) -> pl.DataFrame:
    doc = json.loads(blob)
    sup = doc[0] if doc else {}
    root = (row.get("notes") or "").split("|")[0]
    rows = [
        {
            "root": root,
            "isin": s["isinCode"],
            "asset_issued": s.get("assetIssued"),
            "percentage": _ptbr(s.get("percentage")),
            "price_unit": _ptbr(s.get("priceUnit")),
            "trading_period": s.get("tradingPeriod"),
            "subscription_date": _dmy(s.get("subscriptionDate")),
            "approved_on": _dmy(s.get("approvedOn")),
            "last_date_prior": _dmy(s.get("lastDatePrior")),
            "raw_locator": f"$[0].subscriptions[{i}]",
        }
        for i, s in enumerate(sup.get("subscriptions") or [])
    ]
    return _frame(rows, SUBSCRIPTION, row, ("percentage", "price_unit"))


class B3CompanyEvents(Connector):
    source_id: ClassVar[str] = "b3_company_events"
    version: ClassVar[str] = "1"
    user_agent: ClassVar[str | None] = BROWSER_UA
    contracts: ClassVar[dict[str, Contract]] = CONTRACTS
    dedup_staging: ClassVar[bool] = True  # every refresh re-serves the whole history

    def __init__(self) -> None:
        self._roots: set[str] = set()
        self._last: dict[str, date] = {}
        self._force = False

    def _spec(self, endpoint: str, params: dict[str, Any], dataset: str, locator: str, min_bytes: int = 2) -> FetchSpec:
        return FetchSpec(
            self.source_id,
            dataset,
            f"{BASE}/{endpoint}/{encode({'language': 'pt-br', **params})}",
            "json",
            reference_date=today_brt(),
            conditional=False,
            min_bytes=min_bytes,
            locator=locator,
        )

    @staticmethod
    def universe(zones: Zones) -> set[str]:
        quotes = zones.staging / "b3_cotahist" / "quote"
        if not quotes.exists():
            return set()
        frame = (
            pl.scan_parquet(quotes / "**" / "*.parquet", hive_partitioning=False)
            .filter((pl.col("tpmerc") == 10) & pl.col("ticker").str.contains(r"^[A-Z0-9]{4}\d{1,2}$"))
            .select(pl.col("ticker").str.slice(0, 4).alias("root"))
            .unique()
            .collect()
        )
        return set(frame["root"].to_list())

    def discover(self, mode: Mode, zones: Zones, **options: Any) -> Iterable[FetchSpec]:
        self._roots = set(options.get("tickers") or []) or self.universe(zones)
        self._force = mode is Mode.BACKFILL
        held = held_rows(zones, self.source_id, "supplement")
        self._last = {}
        if held.height:
            for note, at in zip(held["notes"].to_list(), held["fetched_at"].to_list(), strict=True):
                if note:
                    r = note.split("|")[0]
                    self._last[r] = max(self._last.get(r, at.date()), at.date())
        yield self._spec("GetInitialCompanies", {"pageNumber": 1, "pageSize": PAGE}, "companies", "page=1", 50)

    def _due(self, root: str) -> bool:
        last = self._last.get(root)
        return (self._force and last is None) or (
            not self._force and (last is None or today_brt() - last >= timedelta(days=EVERY_DAYS))
        )

    def follow(self, spec: FetchSpec, blob: bytes) -> Iterable[FetchSpec]:
        doc = json.loads(blob)
        params = decode(spec.url)
        if spec.dataset_id == "companies":
            out: list[FetchSpec] = []
            page = int(params["pageNumber"])
            if page == 1:
                for p in range(2, int(doc["page"]["totalPages"] or 1) + 1):
                    out.append(
                        self._spec(
                            "GetInitialCompanies", {"pageNumber": p, "pageSize": PAGE}, "companies", f"page={p}", 50
                        )
                    )
            for r in doc.get("results") or []:
                root, name = r["issuingCompany"], r.get("tradingName") or ""
                if root not in self._roots or not self._due(root):
                    continue
                self._last[root] = today_brt()  # once per root even if it appears twice
                out.append(self._spec("GetListedSupplementCompany", {"issuingCompany": root}, "supplement", root))
                if name.strip():
                    out.append(self._cash(root, name, 1))
            return out
        if spec.dataset_id == "cash":
            pages = int((doc.get("page") or {}).get("totalPages") or 0)
            page = int(params["pageNumber"])
            if page == 1 and pages > 1:
                root = (spec.locator or "").split("|")[0]
                return [self._cash(root, params["tradingName"], p) for p in range(2, pages + 1)]
        return []

    def _cash(self, root: str, name: str, page: int) -> FetchSpec:
        params = {"pageNumber": page, "pageSize": PAGE, "tradingName": name}
        return self._spec("GetListedCashDividends", params, "cash", f"{root}|{name}|page={page}")

    def derive(self, zones: Zones, run: Any) -> None:
        from fin.core import events

        events.build(zones, run)

    def parse(self, blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
        ds = str(row["dataset_id"])
        if ds == "companies":
            yield Parsed("issuer", "all", parse_issuers(blob, row))
        elif ds == "cash":
            yield Parsed("cash_event", "all", parse_cash(blob, row))
        elif ds == "supplement":
            stock, cash = parse_supplement(blob, row)
            yield Parsed("stock_event", "all", stock)
            yield Parsed("cash_announcement", "all", cash)
            yield Parsed("subscription", "all", parse_subscriptions(blob, row))


# ------------------------------------------------------------------------------------------------ Yahoo chart events
# Tier U candidates (docs/sources/yahoo_chart.md): split ratios and dividend amounts with their ex-dates. Yahoo's
# dividend amounts are split-adjusted and do not separate JCP from dividends: they are only cross-checks.

YAHOO_SPLIT = Contract(
    table="staging.yahoo_chart.split",
    version=1,
    description="A split or bonus as Yahoo reports it (tier U candidate).",
    columns=(
        Column("ticker", pl.String, "B3 ticker (symbol without .SA)", "código", nullable=False),
        Column("ex_date", pl.Date, "event date (Yahoo: the ex-date), Brasília", "data ex", "date", nullable=False),
        Column("numerator", pl.Int64, "new shares", "numerador", "shares", nullable=False),
        Column("denominator", pl.Int64, "old shares", "denominador", "shares", nullable=False),
    ),
    rules=(Rule("positive", (pl.col("numerator") > 0) & (pl.col("denominator") > 0)),),
)

YAHOO_DIVIDEND = Contract(
    table="staging.yahoo_chart.dividend",
    version=1,
    description="A cash distribution as Yahoo reports it: split-adjusted, JCP not distinguished (tier U).",
    columns=(
        Column("ticker", pl.String, "B3 ticker", "código", nullable=False),
        Column("ex_date", pl.Date, "ex-date, Brasília", "data ex", "date", nullable=False),
        Column(
            "amount",
            DEC,
            "amount per share, split-adjusted to today",
            "valor",
            "BRL per share (adjusted)",
            nullable=False,
        ),
    ),
)


def parse_yahoo_events(blob: bytes, row: dict[str, Any]) -> tuple[pl.DataFrame, pl.DataFrame]:
    from datetime import UTC, datetime
    from zoneinfo import ZoneInfo

    brt = ZoneInfo("America/Sao_Paulo")
    res = json.loads(blob)["chart"]["result"][0]
    ticker = res["meta"]["symbol"].removesuffix(".SA")
    ev = res.get("events") or {}

    def day(ts: int) -> date:
        return datetime.fromtimestamp(ts, UTC).astimezone(brt).date()

    def ratio(s: dict[str, Any]) -> Fraction:
        """Terms may be decimals (1.2:1 is 6:5): read as the shortest decimal of each double, exactly."""
        return Fraction(Decimal(repr(float(s["numerator"])))) / Fraction(Decimal(repr(float(s["denominator"]))))

    splits = [
        {
            "ticker": ticker,
            "ex_date": day(s["date"]),
            "numerator": ratio(s).numerator,
            "denominator": ratio(s).denominator,
            "raw_locator": f"$.chart.result[0].events.splits.{k}",
        }
        for k, s in sorted((ev.get("splits") or {}).items())
    ]
    divs = [
        {
            "ticker": ticker,
            "ex_date": day(d["date"]),
            "amount": repr(float(d["amount"])),
            "raw_locator": f"$.chart.result[0].events.dividends.{k}",
        }
        for k, d in sorted((ev.get("dividends") or {}).items())
    ]
    return _frame(splits, YAHOO_SPLIT, row, ()), _frame(divs, YAHOO_DIVIDEND, row, ("amount",))
