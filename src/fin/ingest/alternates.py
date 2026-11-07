"""Archive connectors for the routes that close data gaps (gap matrix: docs/evaluation/2026-11-07-data-gap-matrix.md).

Each was verified on 2026-11-07 against real responses (recon notes in docs/sources/). They archive now and parse
later (PLAN §4.13), like the ephemeral snapshots (ADR-0007). Third-party mirrors (`pyield_data`) and unofficial
sources (`yahoo_chart`) are tier S/U: they enter L3 only as candidates or cross-checks (ADR-0010).
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import date, timedelta
from typing import Any, ClassVar

import polars as pl

from fin.config import Zones
from fin.ingest.base import Connector, Mode
from fin.ingest.fetch import FetchSpec
from fin.ingest.http import BROWSER_UA
from fin.ingest.snapshots import today_brt
from fin.store.manifest import Manifest


def _held(zones: Zones, source_id: str, dataset_id: str) -> pl.DataFrame:
    m = Manifest(zones.manifest).read()
    if m.is_empty():
        return m
    return m.filter(
        (pl.col("source_id") == source_id) & (pl.col("dataset_id") == dataset_id) & (pl.col("http_status") == 200)
    )


def _last_fetch(zones: Zones, source_id: str, dataset_id: str) -> date | None:
    m = _held(zones, source_id, dataset_id)
    if m.is_empty():
        return None
    return m["fetched_at"].max().date()  # type: ignore[union-attr]


def month_windows(start: date, end: date) -> list[tuple[date, date]]:
    """Calendar-month windows [first, last] covering start..end, clipped to both ends."""
    out: list[tuple[date, date]] = []
    d = start
    while d <= end:
        nxt = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
        out.append((d, min(nxt - timedelta(days=1), end)))
        d = nxt
    return out


class PyieldData(Connector):
    """A daily-updated public mirror (github.com/crdcj/pyield-data, maintained with the MIT `pyield` library) of
    ANBIMA government-bond indicative rates from 2020-01-02, B3 futures (DI1, DAP, DOL, IND…) from 2018-01-02, and
    the NTN-B VNA. Its bond rows equal ANBIMA's own files on every date we hold (docs/sources/pyield_data.md).
    Fetched on demand (backfill), not daily: our own ANBIMA and B3 archives are the primary from 2026-10-29."""

    source_id: ClassVar[str] = "pyield_data"
    version: ClassVar[str] = "0-archive"
    BASE = "https://github.com/crdcj/pyield-data/releases/latest/download"
    FILES: ClassVar[tuple[str, ...]] = ("anbima_tpf", "b3_futures", "vna_ntnb")

    def discover(self, mode: Mode, zones: Zones, **options: Any) -> Iterable[FetchSpec]:
        if mode is not Mode.BACKFILL:
            return
        for name in self.FILES:
            yield FetchSpec(self.source_id, name, f"{self.BASE}/{name}.parquet", "parquet", reference_date=today_brt())


class Ipeadata(Connector):
    """IPEA's OData API: FGV's IGP-M (1989-06–) and IGP-DI (1944–) index numbers, absent from BCB SGS
    (docs/sources/ipeadata.md). One request returns a whole series; unchanged days dedupe in raw."""

    source_id: ClassVar[str] = "ipeadata"
    version: ClassVar[str] = "0-archive"
    BASE = "https://www.ipeadata.gov.br/api/odata4"
    SERIES: ClassVar[tuple[str, ...]] = ("IGP12_IGPM12", "IGP12_IGPDI12", "IGP12_IGPMG12")

    def discover(self, mode: Mode, zones: Zones, **options: Any) -> Iterable[FetchSpec]:
        for code in self.SERIES:
            yield FetchSpec(
                self.source_id,
                code.lower(),
                f"{self.BASE}/ValoresSerie(SERCODIGO='{code}')",
                "json",
                reference_date=today_brt(),
                conditional=False,
                min_bytes=100,
            )


class TesouroVna(Connector):
    """Tesouro Nacional's monthly VNA tables, NTN-B from 2000-07-15 and NTN-C from 2000-07-01, overwritten at each
    update (docs/sources/tesouro_vna.md). Reproduced exactly from IPCA/IGP-M index numbers in recon."""

    source_id: ClassVar[str] = "tesouro_vna"
    version: ClassVar[str] = "0-archive"
    FILES: ClassVar[dict[str, str]] = {
        "vna_ntnb": "https://thot-arquivos.tesouro.gov.br/publicacao/53360",
        "vna_ntnc": "https://thot-arquivos.tesouro.gov.br/publicacao/45833",
    }

    def discover(self, mode: Mode, zones: Zones, **options: Any) -> Iterable[FetchSpec]:
        for dataset, url in self.FILES.items():
            yield FetchSpec(self.source_id, dataset, url, "xlsx", reference_date=today_brt(), min_bytes=1000)


class BcbSgs(Connector):
    """BCB SGS daily series in ≤ 10-year windows (docs/sources/bcb_sgs.md). CDI (12) and Selic (11) publication
    days from 1986 are also the only business-day record found before ANBIMA's calendar starts in 2001
    (OQ-22). Backfill fetches whole history; otherwise the last 30 days, which catches BCB's one-day lag."""

    source_id: ClassVar[str] = "bcb_sgs"
    version: ClassVar[str] = "0-archive"
    BASE = "https://api.bcb.gov.br/dados/serie"
    SERIES: ClassVar[dict[int, date]] = {  # code -> first date served (measured)
        12: date(1986, 3, 6),  # CDI % a.d.
        11: date(1986, 6, 4),  # Selic % a.d.
        4389: date(1986, 3, 6),  # CDI % a.a. base 252
        1178: date(1986, 6, 4),  # Selic % a.a. base 252
        432: date(1999, 3, 5),  # Copom target
    }
    WINDOW_YEARS = 10

    @staticmethod
    def add_years(d: date, n: int) -> date:
        try:
            return d.replace(year=d.year + n)
        except ValueError:  # 29 February
            return d.replace(year=d.year + n, day=28)

    def windows(self, first: date, end: date) -> list[tuple[date, date]]:
        out: list[tuple[date, date]] = []
        d = first
        while d <= end:
            last = min(self.add_years(d, self.WINDOW_YEARS) - timedelta(days=1), end)
            out.append((d, last))
            d = last + timedelta(days=1)
        return out

    def discover(self, mode: Mode, zones: Zones, **options: Any) -> Iterable[FetchSpec]:
        end = today_brt()
        for code, first in self.SERIES.items():
            start = first if mode is Mode.BACKFILL else end - timedelta(days=30)
            for a, b in self.windows(start, end):
                yield FetchSpec(
                    self.source_id,
                    f"sgs_{code}",
                    f"{self.BASE}/bcdata.sgs.{code}/dados",
                    "json",
                    params={"formato": "json", "dataInicial": f"{a:%d/%m/%Y}", "dataFinal": f"{b:%d/%m/%Y}"},
                    reference_date=b,
                    conditional=False,  # SGS answers unconditional 304s on some forms (docs/sources/bcb_sgs.md)
                    locator=f"{a:%Y-%m-%d}..{b:%Y-%m-%d}",
                )


class SndDebentures(Connector):
    """SND (debentures.com.br), the debenture registry (docs/sources/snd_debentures.md):
    - `caracteristicas`: terms of every debenture issued since 1981, dead ones included; a current snapshot, daily;
    - `agenda`: future interest/amortisation events only (past events are not served): archived weekly;
    - `precos`: secondary-market trade statistics from 1993-11, by calendar month (backfill) or the last 10 days.
    SND's page says its data is migrating to ANBIMA Data (login): every snapshot kept now is a hedge."""

    source_id: ClassVar[str] = "snd_debentures"
    version: ClassVar[str] = "0-archive"
    BASE = "https://www.debentures.com.br/exploreosnd/consultaadados"
    FIRST_PRICES = date(1993, 11, 1)
    AGENDA_EVERY_DAYS = 7

    def _precos(self, a: date, b: date) -> FetchSpec:
        return FetchSpec(
            self.source_id,
            "precos",
            f"{self.BASE}/mercadosecundario/precosdenegociacao_e.asp",
            "txt",
            params={
                "op_exc": "False",
                "emissor": "",
                "ativo": "",
                "ISIN": "",
                # SND reads these as month/day/year (an invalid month is HTTP 500; measured 2026-11-07) and
                # prints dates as day/month/year without zero padding.
                "dt_ini": f"{a:%m/%d/%Y}",
                "dt_fim": f"{b:%m/%d/%Y}",
            },
            reference_date=b,
            conditional=False,
            locator=f"{a:%Y-%m-%d}..{b:%Y-%m-%d}",
        )

    def discover(self, mode: Mode, zones: Zones, **options: Any) -> Iterable[FetchSpec]:
        d = today_brt()
        yield FetchSpec(
            self.source_id,
            "caracteristicas",
            f"{self.BASE}/emissoesdedebentures/caracteristicas_e.asp",
            "txt",
            reference_date=d,
            conditional=False,
            min_bytes=10_000,
        )
        last = _last_fetch(zones, self.source_id, "agenda")
        if last is None or (d - last).days >= self.AGENDA_EVERY_DAYS:
            yield FetchSpec(
                self.source_id,
                "agenda",
                f"{self.BASE}/eventosfinanceiros/agenda_e.asp",
                "txt",
                reference_date=d,
                conditional=False,
                min_bytes=10_000,
            )
        if mode is Mode.BACKFILL:
            rows = _held(zones, self.source_id, "precos")
            held = set(rows["notes"].to_list()) if rows.height else set()
            for a, b in month_windows(self.FIRST_PRICES, d - timedelta(days=1)):
                spec = self._precos(a, b)
                if spec.locator not in held or b >= d - timedelta(days=40):
                    yield spec
        else:
            yield self._precos(d - timedelta(days=10), d - timedelta(days=1))


class FundosNetRendimentos(Connector):
    """B3 Fundos.NET structured notices 'Rendimentos e Amortizações' (category 14, type 41): every FII/Fiagro
    distribution since 2016-11-30, with the minute it was delivered (knowledge time), data-com, payment date and
    value per unit (docs/sources/b3_fundosnet.md). The listing is paged newest first; each notice is a small XML.
    Daily runs page until a whole page is already held; backfill walks every page."""

    source_id: ClassVar[str] = "b3_fundosnet"
    version: ClassVar[str] = "0-archive"
    user_agent: ClassVar[str | None] = BROWSER_UA
    BASE = "https://fnet.bmfbovespa.com.br/fnet/publico"
    PAGE = 200  # 500 is refused with a 302 (measured 2026-11-07)

    def __init__(self) -> None:
        self._held_ids: set[int] = set()
        self._backfill = False

    def _listing(self, offset: int) -> FetchSpec:
        return FetchSpec(
            self.source_id,
            "listagem",
            f"{self.BASE}/pesquisarGerenciadorDocumentosDados",
            "json",
            params={
                "d": 0,
                "s": offset,
                "l": self.PAGE,
                "o[0][dataEntrega]": "desc",
                "idCategoriaDocumento": 14,
                "idTipoDocumento": 41,
            },
            reference_date=today_brt(),
            conditional=False,
            locator=f"offset={offset}",
        )

    def _document(self, doc_id: int) -> FetchSpec:
        return FetchSpec(
            self.source_id,
            "informe_rendimentos",
            f"{self.BASE}/downloadDocumento",
            "xml",
            params={"id": doc_id},
            conditional=False,
            min_bytes=100,
            locator=f"id={doc_id}",
        )

    def discover(self, mode: Mode, zones: Zones, **options: Any) -> Iterable[FetchSpec]:
        held = _held(zones, self.source_id, "informe_rendimentos")
        self._held_ids = {int(n.removeprefix("id=")) for n in held["notes"].to_list()} if held.height else set()
        self._backfill = mode is Mode.BACKFILL
        yield self._listing(0)

    def follow(self, spec: FetchSpec, blob: bytes) -> Iterable[FetchSpec]:
        if spec.dataset_id != "listagem":
            return []
        page = json.loads(blob)
        ids = [int(d["id"]) for d in page.get("data", [])]
        new = [i for i in ids if i not in self._held_ids]
        self._held_ids.update(new)
        out = [self._document(i) for i in new]
        offset = int((spec.params or {})["s"]) + self.PAGE
        more = offset < int(page.get("recordsFiltered") or 0)
        if more and (self._backfill or (ids and len(new) == len(ids))):
            out.append(self._listing(offset))
        return out


class YahooChart(Connector):
    """Yahoo Finance chart endpoint, tier U (PLAN §4.4: cross-check only). Daily prices with split and dividend
    events per ticker; it carries the bonificações B3's events backend misses (OQ-18, verified on ITUB4 2025-03-18
    and 2025-12-26, SLCE3 2023 and 2026). Its facts enter only as candidate events (docs/sources/yahoo_chart.md).
    Default tickers: the standard-lot shares and units, and the FIIs, that traded in COTAHIST in the last year."""

    source_id: ClassVar[str] = "yahoo_chart"
    version: ClassVar[str] = "0-archive"
    user_agent: ClassVar[str | None] = BROWSER_UA
    URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    # COTAHIST CODBDI (layout PDF): 02 standard lot, 08 judicial recovery, 12 FII.
    CODBDI: ClassVar[tuple[str, ...]] = ("02", "08", "12")

    @classmethod
    def recent_tickers(cls, zones: Zones, days: int = 365) -> list[str]:
        quotes = zones.staging / "b3_cotahist" / "quote"
        since = today_brt() - timedelta(days=days)
        frame = (
            pl.scan_parquet(quotes / "**" / "*.parquet", hive_partitioning=False)
            .filter((pl.col("trade_date") >= since) & (pl.col("tpmerc") == 10) & pl.col("codbdi").is_in(cls.CODBDI))
            .select("ticker")
            .unique()
            .collect()
        )
        return sorted(frame["ticker"].to_list())

    def discover(self, mode: Mode, zones: Zones, **options: Any) -> Iterable[FetchSpec]:
        tickers = options.get("tickers") or self.recent_tickers(zones)
        for t in tickers:
            yield FetchSpec(
                self.source_id,
                "chart",
                self.URL.format(symbol=f"{t}.SA"),
                "json",
                params={"range": "max", "interval": "1d", "events": "div|split"},
                reference_date=today_brt(),
                conditional=False,
                absent_status=frozenset({404}),
                locator=t,
            )
