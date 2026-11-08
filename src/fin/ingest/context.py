"""Archive connectors for the context-data catalogue (`reference/context_series.toml`, ADR-0011).

Every entry is a verified free route (docs/sources/context_br.md, context_global.md). One connector class per
source_id is generated from the catalogue. They archive now and parse later (PLAN §4.13).

Cadence: the daily job re-requests an entry when its last fetch is `every_days` old; a per-year file below the
current year is fetched by backfill only. Outside backfill, an entry with `incremental` params asks only for
the last 30 days once its full history is held.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import cache
from pathlib import Path
from typing import Any, ClassVar, cast
from urllib.parse import quote, urlencode

from fin.config import Zones
from fin.ingest import series
from fin.ingest.base import Connector, Mode
from fin.ingest.fetch import FetchSpec
from fin.ingest.http import BROWSER_UA
from fin.ingest.snapshots import archived_dates, calendar_for, today_brt
from fin.ingest.snapshots import held_rows as _held

CATALOGUE = Path(__file__).parents[1] / "reference" / "context_series.toml"
INCREMENTAL_DAYS = 30


@dataclass(frozen=True)
class Entry:
    source: str
    dataset: str
    url: str
    ext: str
    about: str
    every_days: int = 1
    browser: bool = False
    first_year: int | None = None
    keys: tuple[str, ...] = ()
    params: dict[str, str] = field(default_factory=lambda: {})
    incremental: dict[str, str] = field(default_factory=lambda: {})


@cache
def catalogue() -> tuple[Entry, ...]:
    raw = tomllib.loads(CATALOGUE.read_text(encoding="utf-8"))
    out: list[Entry] = []
    for e in raw["file"]:
        out.append(
            Entry(
                source=e["source"],
                dataset=e["dataset"],
                url=e["url"],
                ext=e["ext"],
                about=e["about"],
                every_days=int(e.get("every_days", 1)),
                browser=bool(e.get("browser", False)),
                first_year=e.get("first_year"),
                keys=tuple(e.get("keys", ())),
                params={k: str(v) for k, v in e.get("params", {}).items()},
                incremental={k: str(v) for k, v in e.get("incremental", {}).items()},
            )
        )
    return tuple(out)


def _fill(template: str, key: str | None, year: int | None, since: date) -> str:
    return (
        template.replace("{key}", key or "")
        .replace("{year}", str(year) if year is not None else "")
        .replace("{since}", since.isoformat())
    )


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


@dataclass(frozen=True)
class Planned:
    entry: Entry
    key: str | None
    year: int | None

    @property
    def locator(self) -> str:
        return "|".join(x for x in (self.key, str(self.year) if self.year else None) if x) or "-"

    @property
    def dataset_id(self) -> str:
        return _slug(_fill(self.entry.dataset, self.key, self.year, date.min).replace("_{year}", ""))


def expand(entry: Entry, today: date) -> Iterator[Planned]:
    years: list[int | None] = list(range(entry.first_year, today.year + 1)) if entry.first_year is not None else [None]
    keys: list[str | None] = list(entry.keys) or [None]
    for key in keys:
        for year in years:
            yield Planned(entry, key, year)


class ContextConnector(Connector):
    version: ClassVar[str] = "0-archive"

    def entries(self) -> list[Entry]:
        return [e for e in catalogue() if e.source == self.source_id]

    def _spec(self, p: Planned, today: date, incremental: bool) -> FetchSpec:
        since = today - timedelta(days=INCREMENTAL_DAYS)
        params = p.entry.incremental if incremental and p.entry.incremental else p.entry.params
        query = {k: _fill(v, p.key, p.year, since) for k, v in params.items()}
        url = _fill(p.entry.url, p.key, p.year, since)
        if any(" " in v for v in query.values()):
            # OData (BCB Olinda) rejects '+' for a space with HTTP 400 and accepts %20 (measured 2026-11-07)
            url, query = f"{url}?{urlencode(query, quote_via=quote, safe="$'")}", {}
        return FetchSpec(
            self.source_id,
            p.dataset_id,
            url,
            p.entry.ext,
            params=query or None,
            reference_date=date(p.year, 12, 31) if p.year and p.year < today.year else today,
            conditional=not params and not query,  # a query answer has no stable validators
            absent_status=frozenset({404}),
            min_bytes=50,
            locator=p.locator + ("|since" if incremental and p.entry.incremental else ""),
        )

    def discover(self, mode: Mode, zones: Zones, **options: Any) -> Iterable[FetchSpec]:
        today = today_brt()
        for entry in self.entries():
            plans = list(expand(entry, today))
            held = _held(zones, self.source_id, plans[0].dataset_id) if len(plans) == 1 else None
            for p in plans:
                rows = held if held is not None else _held(zones, self.source_id, p.dataset_id)
                last = None
                if rows.height:
                    mine = [
                        at.date()
                        for note, at in zip(rows["notes"].to_list(), rows["fetched_at"].to_list(), strict=True)
                        if note is not None and note.split("|since")[0] == p.locator
                    ]
                    last = max(mine) if mine else None
                past_year = p.year is not None and p.year < today.year
                if mode is Mode.BACKFILL:
                    if last is None or not past_year:
                        yield self._spec(p, today, incremental=False)
                elif not past_year and (last is None or (today - last).days >= entry.every_days):
                    yield self._spec(p, today, incremental=last is not None)

    def follow(self, spec: FetchSpec, blob: bytes) -> Iterable[FetchSpec]:
        if spec.dataset_id != "commodity_markets_page":
            return ()
        m = re.search(rb'href="([^"]*CMO-Historical-Data-Monthly\.xlsx)"', blob)
        if not m:
            raise ValueError("World Bank page: no CMO-Historical-Data-Monthly.xlsx link (layout changed?)")
        url = m.group(1).decode()
        url = url if url.startswith("http") else f"https://www.worldbank.org{url}"
        return [
            FetchSpec(
                self.source_id,
                "cmo_historical_monthly",
                url,
                "xlsx",
                reference_date=spec.reference_date,
                min_bytes=10_000,
                notes="link read from the commodity-markets page fetched just before",
            )
        ]


class ImaConnector(ContextConnector):
    """`anbima_ima`: the XML of today (portfolio included, ephemeral) plus the historical Quadro Resumo, which ANBIMA
    serves for any business day since 2001-12-04 (docs/sources/anbima_ima.md). Backfill asks for every day not held;
    a normal run re-asks the last 10 business days. The server answers a whole session with its first date, so the
    client drops cookies after each request (`stateless`)."""

    FORM = "https://www.anbima.com.br/informacoes/ima/"
    FIRST_DAY = date(2001, 12, 4)
    LOOKBACK_BUSINESS_DAYS = 10
    stateless: ClassVar[bool] = True
    min_interval: ClassVar[float] = 0.5

    def discover(self, mode: Mode, zones: Zones, **options: Any) -> Iterable[FetchSpec]:
        yield from super().discover(mode, zones, **options)
        cal = calendar_for(zones)
        end = cal.preceding(today_brt())
        if mode is Mode.BACKFILL:
            have = archived_dates(zones, self.source_id, "ima_sh_txt")
            days = [d for d in cal.business_days(self.FIRST_DAY, end) if d not in have]
        else:
            days = cal.business_days(cal.add_business_days(end, -self.LOOKBACK_BUSINESS_DAYS), end)
        for d in reversed(days):
            yield FetchSpec(
                self.source_id,
                "ima_sh_txt",
                f"{self.FORM}ima-sh-down.asp",
                "txt",
                method="POST",
                data={
                    "escolha": "2",
                    "Idioma": "PT",
                    "saida": "txt",
                    "Dt_Ref": f"{d:%d/%m/%Y}",
                    "Dt_Ref_Ver": f"{d:%Y%m%d}",
                },
                headers={"Referer": f"{self.FORM}ima-sh.asp"},
                reference_date=d,
                conditional=False,
                min_bytes=400,  # the 134-byte "no data" stub
                absent_status=frozenset({404}),
            )


def _parse_with(parser: Any) -> Any:
    def parse(self: Connector, blob: bytes, row: dict[str, Any]) -> Iterable[Any]:
        return parser(blob, row)

    return parse


def _derive(self: Connector, zones: Zones, run: Any) -> None:
    series.build_core(zones, self.source_id, run)


def context_connectors() -> list[type[Connector]]:
    """One generated class per source in the catalogue (registry: `ingest/registry.py`)."""
    out: list[type[Connector]] = []
    for sid in dict.fromkeys(e.source for e in catalogue()):
        if sid in {"bcb_sgs", "ipeadata", "ibge_sidra"}:
            continue  # these sources already have a connector; their catalogue entries are merged in there
        browser = any(e.browser for e in catalogue() if e.source == sid)
        attrs: dict[str, Any] = {"source_id": sid, "user_agent": BROWSER_UA if browser else None}
        if sid == "cftc_cot":  # positions are their own staging table (ingest/cftc.py)
            from fin.ingest import cftc

            attrs |= {
                "version": "1",
                "contracts": cftc.CONTRACTS,
                "parse": _parse_with(cftc.parse_payload),
                "dedup_staging": True,
            }
            out.append(type(f"Context_{sid}", (ContextConnector,), attrs))
            continue
        if sid == "bcb_copom":  # decisions are their own staging table (ingest/copom.py)
            from fin.ingest import copom

            attrs |= {
                "version": "1",
                "contracts": copom.CONTRACTS,
                "parse": _parse_with(copom.parse_payload),
                "dedup_staging": True,
            }
            out.append(type(f"Context_{sid}", (ContextConnector,), attrs))
            continue
        if sid == "bcb_focus":  # expectations are their own staging table, not series (ingest/focus.py)
            from fin.ingest import focus

            attrs |= {"version": "1", "contracts": focus.CONTRACTS, "parse": _parse_with(focus.parse_payload),
                      "dedup_staging": True}  # fmt: skip
            out.append(type(f"Context_{sid}", (ContextConnector,), attrs))
            continue
        parser = series.CATALOGUE_PARSERS.get(sid)
        if parser is not None:  # parsed into series_observation (ADR-0013)
            attrs |= {
                "version": "1",
                "contracts": series.CONTRACTS,
                "parse": _parse_with(parser),
                "derive": _derive,
                "dedup_staging": True,
            }
        base: type[ContextConnector] = ImaConnector if sid == "anbima_ima" else ContextConnector
        out.append(cast("type[Connector]", type(f"Context_{sid}", (base,), attrs)))
    return out
