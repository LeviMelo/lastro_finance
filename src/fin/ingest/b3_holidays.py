"""B3's trading calendar page (docs/sources/b3_holidays.md): the days B3 does not trade, published ahead.

`https://www.b3.com.br/pt_br/solucoes/plataformas/puma-trading-system/para-participantes-e-traders/calendario-de-negociacao/feriados/`
is one HTML page with a section per year ("Calendário do mercado YYYY", 2021 onward measured 2026-11-08), a heading per
month and a table per month: day, event, description. The description says per market segment what happens; the
equities closure is the sentence "Não haverá negociação nos mercados de renda variável". Foreign holidays (US) appear
too: on those B3 trades, with some settlement changes.

Staging `market_day`: one row per (date, event) as published, with `equities_closed` and `special_hours` read from
the description. It feeds `calendar_day.is_b3_trading_day` for dates after the last observed session (OQ-1).
"""

from __future__ import annotations

import html
import re
from collections.abc import Iterable
from datetime import date
from typing import Any, ClassVar

import polars as pl

from fin.config import Zones
from fin.ingest.base import Connector, Mode, Parsed
from fin.ingest.fetch import FetchSpec
from fin.ingest.http import BROWSER_UA
from fin.schema import Column, Contract

URL = (
    "https://www.b3.com.br/pt_br/solucoes/plataformas/puma-trading-system/para-participantes-e-traders/"
    "calendario-de-negociacao/feriados/"
)
MONTHS = {m: i for i, m in enumerate(
    ("Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro",
     "Novembro", "Dezembro"), start=1)}  # fmt: skip
CLOSED = re.compile(r"não haverá negociação nos mercados de renda variável", re.IGNORECASE)
SPECIAL = re.compile(r"horário especial|horário diferenciado", re.IGNORECASE)

MARKET_DAY = Contract(
    table="staging.b3_holidays.market_day",
    version=1,
    description="A day B3's trading calendar lists: a Brazilian or foreign holiday, or special hours.",
    columns=(
        Column("date", pl.Date, "the listed day", "data", "date", nullable=False),
        Column("event", pl.String, "Evento as written", "evento", nullable=False),
        Column(
            "equities_closed",
            pl.Boolean,
            "the description says equities do not trade",
            "renda variável fechada",
            nullable=False,
        ),
        Column(
            "special_hours",
            pl.Boolean,
            "the event or description announces special trading hours",
            "horário especial",
            nullable=False,
        ),
        Column("description", pl.String, "Descrição as written (tags removed)", "descrição"),
    ),
)
CONTRACTS = {"market_day": MARKET_DAY}


class LayoutError(ValueError):
    pass


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).replace("\xa0", " ").strip()


def parse_page(blob: bytes, row: dict[str, Any]) -> pl.DataFrame:
    page = blob.decode("utf-8", errors="strict")
    years = [(m.start(), int(m.group(1))) for m in re.finditer(r"Calendário do mercado (\d{4})", page)]
    if not years:
        raise LayoutError("B3 holidays: no 'Calendário do mercado YYYY' section")
    months = [(m.start(), MONTHS[m.group(1)]) for m in re.finditer(r">\s*(" + "|".join(MONTHS) + r")\s*<", page)]
    out: list[dict[str, Any]] = []
    for t in re.finditer(r"<table.*?</table>", page, re.S):
        y = max((v for p, v in years if p < t.start()), default=None)
        mo = max(((p, v) for p, v in months if p < t.start()), default=(None, None))
        if y is None or mo[1] is None:
            continue
        rows = re.findall(r"<tr.*?</tr>", t.group(0), re.S)
        head = [_text(c) for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", rows[0], re.S)] if rows else []
        if head[:2] != ["Dia", "Evento"]:
            raise LayoutError(f"B3 holidays: table header {head}")
        for i, r in enumerate(rows[1:], start=1):
            cells = [_text(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)]
            if len(cells) < 2 or not cells[0].isdigit():
                continue
            desc = " ".join(cells[2:]) if len(cells) > 2 else ""
            out.append({
                "date": date(y, mo[1], int(cells[0])), "event": cells[1],
                "equities_closed": bool(CLOSED.search(desc)), "special_hours": bool(SPECIAL.search(cells[1] + desc)),
                "description": desc or None, "raw_locator": f"year={y};month={mo[1]};table@{t.start()};row={i}",
            })  # fmt: skip
    if not out:
        raise LayoutError("B3 holidays: no rows")
    schema = {c.name: c.dtype for c in MARKET_DAY.columns} | {"raw_locator": pl.String}
    return pl.DataFrame(out, schema=schema, orient="row").with_columns(
        pl.lit(row["raw_sha256"]).alias("raw_sha256"), pl.lit(row["ingest_run_id"]).alias("ingest_run_id")
    )


class B3Holidays(Connector):
    """B3's trading calendar page, fetched daily (conditionally): it carries the coming year's closures."""

    source_id: ClassVar[str] = "b3_holidays"
    version: ClassVar[str] = "1"
    user_agent: ClassVar[str | None] = BROWSER_UA
    contracts: ClassVar[dict[str, Any]] = CONTRACTS
    dedup_staging: ClassVar[bool] = True

    def discover(self, mode: Mode, zones: Zones, **options: Any) -> Iterable[FetchSpec]:
        from fin.ingest.snapshots import today_brt

        yield FetchSpec(self.source_id, "feriados", URL, "html", reference_date=today_brt(), min_bytes=10_000)

    def parse(self, blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
        yield Parsed("market_day", "all", parse_page(blob, row))
