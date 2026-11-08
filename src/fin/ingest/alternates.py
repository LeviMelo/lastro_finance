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
from fin.ingest import (
    b3_events,
    cvm_fca,
    cvm_fre,
    cvm_ipe,
    cvm_statements,
    cvm_vlmo,
    fundosnet,
    fundosnet_cda,
    fundosnet_daily,
    pyield,
    series,
    snd,
)
from fin.ingest.base import Connector, Mode, Parsed
from fin.ingest.context import ContextConnector, catalogue
from fin.ingest.fetch import FetchSpec
from fin.ingest.http import BROWSER_UA
from fin.ingest.snapshots import held_rows as _held
from fin.ingest.snapshots import today_brt


def _last_fetch(zones: Zones, source_id: str, dataset_id: str) -> date | None:
    m = _held(zones, source_id, dataset_id)
    if m.is_empty():
        return None
    return m["fetched_at"].max().date()  # type: ignore[union-attr]


META_EVERY_DAYS = 30


def _meta_due(zones: Zones, source_id: str, dataset_id: str, locator: str, mode: Mode) -> bool:
    """Series metadata is re-requested on backfill and when this code's last copy is a month old."""
    if mode is Mode.BACKFILL:
        return True
    m = _held(zones, source_id, dataset_id)
    if m.is_empty():
        return True
    m = m.filter(pl.col("notes") == locator)
    seen = [at.date() for at in m["fetched_at"].to_list()]
    return not seen or (today_brt() - max(seen)).days >= META_EVERY_DAYS


class SeriesConnector(ContextConnector):
    """A context source whose payloads are parsed into staging series and core `series_observation`
    (`ingest/series.py`)."""

    contracts: ClassVar[dict[str, Any]] = series.CONTRACTS
    dedup_staging: ClassVar[bool] = True

    def derive(self, zones: Zones, run: Any) -> None:
        series.build_core(zones, self.source_id, run)


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
    version: ClassVar[str] = "1"
    contracts: ClassVar[dict[str, Any]] = pyield.CONTRACTS
    dedup_staging: ClassVar[bool] = True  # each release re-ships the whole history

    def parse(self, blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
        return pyield.parse_payload(blob, row)

    BASE = "https://github.com/crdcj/pyield-data/releases/latest/download"
    FILES: ClassVar[tuple[str, ...]] = ("anbima_tpf", "b3_futures", "vna_ntnb")

    def discover(self, mode: Mode, zones: Zones, **options: Any) -> Iterable[FetchSpec]:
        if mode is not Mode.BACKFILL:
            return
        for name in self.FILES:
            yield FetchSpec(self.source_id, name, f"{self.BASE}/{name}.parquet", "parquet", reference_date=today_brt())


class Ipeadata(SeriesConnector):
    """IPEA's OData API: FGV's IGP-M (1989-06–) and IGP-DI (1944–) index numbers, absent from BCB SGS
    (docs/sources/ipeadata.md). One request returns a whole series; unchanged days dedupe in raw."""

    source_id: ClassVar[str] = "ipeadata"
    version: ClassVar[str] = "1"
    BASE = "https://www.ipeadata.gov.br/api/odata4"
    SERIES: ClassVar[tuple[str, ...]] = ("IGP12_IGPM12", "IGP12_IGPDI12", "IGP12_IGPMG12")

    def codes(self) -> list[str]:
        return [*self.SERIES, *(k for e in catalogue() if e.source == self.source_id for k in e.keys)]

    def parse(self, blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
        return series.parse_ipeadata_payload(blob, row)

    def discover(self, mode: Mode, zones: Zones, **options: Any) -> Iterable[FetchSpec]:
        yield from super().discover(mode, zones, **options)  # catalogue entries (reference/context_series.toml)
        for code in self.codes():
            if _meta_due(zones, self.source_id, f"meta_{code.lower()}", code, mode):
                yield FetchSpec(
                    self.source_id,
                    f"meta_{code.lower()}",
                    f"{self.BASE}/Metadados('{code}')",
                    "json",
                    reference_date=today_brt(),
                    conditional=False,
                    min_bytes=100,
                    locator=code,
                )
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


class IbgeSidra(SeriesConnector):
    """IBGE SIDRA tables of the context catalogue; each payload names its variables, periods and units."""

    source_id: ClassVar[str] = "ibge_sidra"
    version: ClassVar[str] = "1"

    def parse(self, blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
        return series.parse_sidra_payload(blob, row)


class TesouroVna(Connector):
    """Tesouro Nacional's monthly VNA tables, NTN-B from 2000-07-15 and NTN-C from 2000-07-01, overwritten at each
    update (docs/sources/tesouro_vna.md). Reproduced exactly from IPCA/IGP-M index numbers in recon. Parsed into
    `series_observation` (`tesouro_vna:NTN-B`, `tesouro_vna:NTN-C/<maturities>`)."""

    source_id: ClassVar[str] = "tesouro_vna"
    version: ClassVar[str] = "1"
    contracts: ClassVar[dict[str, Any]] = series.CONTRACTS
    dedup_staging: ClassVar[bool] = True

    def parse(self, blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
        return series.parse_tesouro_vna_payload(blob, row)

    def derive(self, zones: Zones, run: Any) -> None:
        series.build_core(zones, self.source_id, run)

    FILES: ClassVar[dict[str, str]] = {
        "vna_ntnb": "https://thot-arquivos.tesouro.gov.br/publicacao/53360",
        "vna_ntnc": "https://thot-arquivos.tesouro.gov.br/publicacao/45833",
    }

    def discover(self, mode: Mode, zones: Zones, **options: Any) -> Iterable[FetchSpec]:
        for dataset, url in self.FILES.items():
            yield FetchSpec(self.source_id, dataset, url, "xlsx", reference_date=today_brt(), min_bytes=1000)


class BcbSgs(SeriesConnector):
    """BCB SGS daily series in ≤ 10-year windows (docs/sources/bcb_sgs.md). CDI (12) and Selic (11) publication
    days from 1986 are also the only business-day record found before ANBIMA's calendar starts in 2001
    (OQ-22). Backfill fetches whole history; otherwise the last 30 days, which catches BCB's one-day lag."""

    source_id: ClassVar[str] = "bcb_sgs"
    version: ClassVar[str] = "1"
    BASE = "https://api.bcb.gov.br/dados/serie"

    def derive(self, zones: Zones, run: Any) -> None:
        series.build_core(zones, self.source_id, run)
        from fin.ingest.anbima_calendar import build_calendar

        build_calendar(zones, run)  # the calendar before 2001 is SGS 12's publication days (OQ-22)

    # names, frequency and unit per code: the legacy SOAP service (CKAN lacks 11 of our codes; measured 2026-11-07)
    META_URL = "https://www3.bcb.gov.br/wssgs/services/FachadaWSSGS"
    SERIES: ClassVar[dict[int, date]] = {  # code -> first date served (measured)
        12: date(1986, 3, 6),  # CDI % a.d.
        11: date(1986, 6, 4),  # Selic % a.d.
        4389: date(1986, 3, 6),  # CDI % a.a. base 252
        4391: date(1986, 8, 1),  # CDI accumulated in the month, % a.m. (measured 2026-11-08; checks SGS 12)
        1178: date(1986, 6, 4),  # Selic % a.a. base 252
        432: date(1999, 3, 5),  # Copom target
        226: date(1991, 2, 1),  # TR, % per period (row = start date, dataFim = +1 month); start not verified
        195: date(2012, 5, 4),  # poupança from 2012-05-04, % a.m.
        25: date(1991, 2, 1),  # poupança until 2012-05-03, % a.m.
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

    def codes(self) -> list[str]:
        return [*(str(c) for c in self.SERIES), *(k for e in catalogue() if e.source == self.source_id for k in e.keys)]

    def parse(self, blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
        return series.parse_sgs_payload(blob, row)

    def discover(self, mode: Mode, zones: Zones, **options: Any) -> Iterable[FetchSpec]:
        yield from super().discover(mode, zones, **options)  # monthly series of the context catalogue
        for code in self.codes():
            if _meta_due(zones, self.source_id, "sgs_meta", code, mode):
                yield FetchSpec(
                    self.source_id,
                    "sgs_meta",
                    self.META_URL,
                    "xml",
                    method="POST",
                    content=series.sgs_meta_envelope(code),
                    headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": '""'},
                    reference_date=today_brt(),
                    conditional=False,
                    min_bytes=200,
                    locator=code,
                )
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
                    content_types=("application/json",),  # its gateway serves error pages as HTTP 200
                    locator=f"{a:%Y-%m-%d}..{b:%Y-%m-%d}",
                )


class SndDebentures(Connector):
    """SND (debentures.com.br), the debenture registry (docs/sources/snd_debentures.md):
    - `caracteristicas`: terms of every debenture issued since 1981, dead ones included; a current snapshot, daily;
    - `agenda`: future interest/amortisation events only (past events are not served): archived weekly;
    - `precos`: secondary-market trade statistics from 1993-11, by calendar month (backfill) or the last 10 days.
    SND's page says its data is migrating to ANBIMA Data (login): every snapshot kept now is a hedge."""

    source_id: ClassVar[str] = "snd_debentures"
    version: ClassVar[str] = "1"
    contracts: ClassVar[dict[str, Any]] = snd.CONTRACTS
    dedup_staging: ClassVar[bool] = True  # terms are re-sent whole daily; price ranges overlap
    BASE = "https://www.debentures.com.br/exploreosnd/consultaadados"
    FIRST_PRICES = date(1993, 11, 1)
    AGENDA_EVERY_DAYS = 7

    def parse(self, blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
        if row["dataset_id"] == "caracteristicas":
            return snd.parse_terms(blob, row)
        if row["dataset_id"] == "precos":
            return snd.parse_prices(blob, row)
        return ()  # `agenda` is archived, not parsed yet

    def derive(self, zones: Zones, run: Any) -> None:
        from fin.core import debentures

        debentures.build(zones, run)

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
            # A month whose export failed is fetched day by day: one bad day makes SND answer 500 for any range
            # containing it (2020-12-16 and 2021-04-09, measured 2026-11-07), and only that day stays missing.
            first_pass = not held
            for a, b in month_windows(self.FIRST_PRICES, d - timedelta(days=1)):
                spec = self._precos(a, b)
                if spec.locator in held and b < d - timedelta(days=40):
                    continue
                if first_pass or b >= d - timedelta(days=40):
                    yield spec
                    continue
                for k in range((b - a).days + 1):
                    day = a + timedelta(days=k)
                    one = self._precos(day, day)
                    if one.locator not in held:
                        yield one
        else:
            yield self._precos(d - timedelta(days=10), d - timedelta(days=1))


class FundosNetRendimentos(Connector):
    """B3 Fundos.NET structured notices 'Rendimentos e Amortizações' (category 14, type 41): every FII/Fiagro
    distribution since 2016-11-30, with the minute it was delivered (knowledge time), data-com, payment date and
    value per unit (docs/sources/b3_fundosnet.md). The listing is paged newest first; each notice is a small XML.
    Daily runs page until a whole page is already held; backfill walks every page."""

    source_id: ClassVar[str] = "b3_fundosnet"
    version: ClassVar[str] = "1"
    user_agent: ClassVar[str | None] = BROWSER_UA
    contracts: ClassVar[dict[str, Any]] = fundosnet.CONTRACTS
    dedup_staging: ClassVar[bool] = True  # listing pages overlap
    BASE = "https://fnet.bmfbovespa.com.br/fnet/publico"
    PAGE = 200  # 500 is refused with a 302 (measured 2026-11-07)
    concurrency: ClassVar[int] = 8  # one small XML per notice; latency, not bandwidth, bounds it (ADR-0023)
    min_interval: ClassVar[float] = 0.05
    CATEGORY: ClassVar[int] = 14
    TYPE: ClassVar[int] = 41
    DOCUMENT: ClassVar[str] = "informe_rendimentos"
    FUND_TYPES: ClassVar[tuple[int | None, ...]] = (None,)  # Fundos.NET `tipoFundo` filters, each paged on its own

    def __init__(self) -> None:
        self._held_ids: set[int] = set()
        self._backfill = False

    def _listing(self, offset: int, fund_type: int | None = None) -> FetchSpec:
        extra = {} if fund_type is None else {"tipoFundo": fund_type}
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
                "idCategoriaDocumento": self.CATEGORY,
                "idTipoDocumento": self.TYPE,
                **extra,
            },
            reference_date=today_brt(),
            conditional=False,
            locator=f"offset={offset}" if fund_type is None else f"tipoFundo={fund_type};offset={offset}",
        )

    def _document(self, doc_id: int) -> FetchSpec:
        return FetchSpec(
            self.source_id,
            self.DOCUMENT,
            f"{self.BASE}/downloadDocumento",
            "xml",
            params={"id": doc_id},
            conditional=False,
            min_bytes=100,
            locator=f"id={doc_id}",
        )

    def discover(self, mode: Mode, zones: Zones, **options: Any) -> Iterable[FetchSpec]:
        held = _held(zones, self.source_id, self.DOCUMENT)
        self._held_ids = {int(n.removeprefix("id=")) for n in held["notes"].to_list()} if held.height else set()
        self._backfill = mode is Mode.BACKFILL
        for t in self.FUND_TYPES:
            yield self._listing(0, t)

    def parse(self, blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
        return fundosnet.parse_payload(blob, row)

    def derive(self, zones: Zones, run: Any) -> None:
        from fin.core import events

        events.build(zones, run)

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
            t = (spec.params or {}).get("tipoFundo")
            out.append(self._listing(offset, None if t is None else int(t)))
        return out


class FundosNetInformeDiario(FundosNetRendimentos):
    """B3 Fundos.NET 'Informe Diário' (category 6, type 64): every ETF's daily NAV per quota, net assets and flows
    since 2018-06-29, which CVM's open data stopped carrying in 2018-09 (docs/sources/b3_fundosnet_daily.md)."""

    source_id: ClassVar[str] = "b3_fundosnet_daily"
    contracts: ClassVar[dict[str, Any]] = fundosnet_daily.CONTRACTS
    CATEGORY: ClassVar[int] = 6
    TYPE: ClassVar[int] = 64
    DOCUMENT: ClassVar[str] = "informe_diario"

    def parse(self, blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
        return fundosnet_daily.parse_payload(blob, row)

    def derive(self, zones: Zones, run: Any) -> None:
        return None


class FundosNetCda(FundosNetInformeDiario):
    """B3 Fundos.NET 'Composição da Carteira (CDA)' (category 6, type 63) of ETFs: the monthly portfolio, which CVM's
    open-data CDA does not carry for ETFs (docs/sources/b3_fundosnet_cda.md). Type 63 also holds FIDC portfolios,
    so the listing is filtered by fund type: 3 (ETF) and 4 (ETF RF)."""

    source_id: ClassVar[str] = "b3_fundosnet_cda"
    contracts: ClassVar[dict[str, Any]] = fundosnet_cda.CONTRACTS
    TYPE: ClassVar[int] = 63
    DOCUMENT: ClassVar[str] = "carteira"
    FUND_TYPES: ClassVar[tuple[int | None, ...]] = (3, 4)

    def parse(self, blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
        return fundosnet_cda.parse_payload(blob, row)


class YahooChart(Connector):
    """Yahoo Finance chart endpoint, tier U (PLAN §4.4: cross-check only). Daily prices with split and dividend
    events per ticker; it carries the bonificações B3's events backend misses (OQ-18, verified on ITUB4 2025-03-18
    and 2025-12-26, SLCE3 2023 and 2026). Its facts enter only as candidate events (docs/sources/yahoo_chart.md).
    Default tickers: the standard-lot shares and units, and the FIIs, that traded in COTAHIST in the last year."""

    source_id: ClassVar[str] = "yahoo_chart"
    version: ClassVar[str] = "1"
    contracts: ClassVar[dict[str, Any]] = {"split": b3_events.YAHOO_SPLIT, "dividend": b3_events.YAHOO_DIVIDEND}
    dedup_staging: ClassVar[bool] = True

    def derive(self, zones: Zones, run: Any) -> None:
        from fin.core import events

        events.build(zones, run)

    def parse(self, blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
        splits, dividends = b3_events.parse_yahoo_events(blob, row)
        yield Parsed("split", "all", splits)
        yield Parsed("dividend", "all", dividends)

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


class _CvmCompanyDocs(Connector):
    """CVM's yearly company-document zips (dados.cvm.gov.br/dados/CIA_ABERTA/DOC/<KIND>/DADOS/). The last ~5 years
    are rewritten weekly and keep **only the latest version** of each filing (docs/sources/cvm_dfp_itr.md), so a
    restated number is lost unless the file is archived before the restatement. Backfill takes every year once;
    the daily job re-requests (conditionally: an unchanged file is a 304) the current and previous year weekly and
    the three years before monthly."""

    version: ClassVar[str] = "0-archive"
    KINDS: ClassVar[dict[str, int]] = {}  # kind -> first year served
    WEEKLY_YEARS = 2
    MONTHLY_YEARS = 5
    BASE = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC"

    def _spec(self, kind: str, year: int) -> FetchSpec:
        k = kind.lower()
        return FetchSpec(
            self.source_id,
            f"{k}_cia_aberta",
            f"{self.BASE}/{kind}/DADOS/{k}_cia_aberta_{year}.zip",
            "zip",
            reference_date=date(year, 12, 31),
            absent_status=frozenset({404}),
            locator=str(year),
            unpack_members=True,  # re-shipped weekly: stored as member deltas (ADR-0014)
        )

    def discover(self, mode: Mode, zones: Zones, **options: Any) -> Iterable[FetchSpec]:
        today = today_brt()
        for kind, first in self.KINDS.items():
            years = options.get("years") or list(range(first, today.year + 1))
            held = _held(zones, self.source_id, f"{kind.lower()}_cia_aberta")
            last: dict[str, date] = {}
            if held.height:
                for note, at in zip(held["notes"].to_list(), held["fetched_at"].to_list(), strict=True):
                    last[note] = max(last.get(note, at.date()), at.date())
            for year in years:
                seen = last.get(str(year))
                age = today.year - year
                if mode is Mode.BACKFILL and seen is None:
                    yield self._spec(kind, year)
                elif mode is not Mode.BACKFILL and age < self.MONTHLY_YEARS:
                    every = 7 if age < self.WEEKLY_YEARS else 30
                    if seen is None or (today - seen).days >= every:
                        yield self._spec(kind, year)


class CvmDfpItr(_CvmCompanyDocs):
    """Parsed to staging `statement_line`, `document`, `share_capital` (`ingest/cvm_statements.py`)."""

    source_id: ClassVar[str] = "cvm_dfp_itr"
    version: ClassVar[str] = "1"
    KINDS: ClassVar[dict[str, int]] = {"DFP": 2010, "ITR": 2011}
    contracts: ClassVar[dict[str, Any]] = cvm_statements.CONTRACTS
    dedup_staging: ClassVar[bool] = True

    def parse(self, blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
        return cvm_statements.parse_payload(blob, row)

    def derive(self, zones: Zones, run: Any) -> None:
        from fin.core import shares

        shares.build(zones, run)


class CvmFca(_CvmCompanyDocs):
    """Parsed to staging `document`, `company`, `security` (`ingest/cvm_fca.py`): the CNPJ -> ticker evidence."""

    source_id: ClassVar[str] = "cvm_fca"
    version: ClassVar[str] = "1"
    KINDS: ClassVar[dict[str, int]] = {"FCA": 2010}
    contracts: ClassVar[dict[str, Any]] = cvm_fca.CONTRACTS
    dedup_staging: ClassVar[bool] = True

    def parse(self, blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
        return cvm_fca.parse_payload(blob, row)


class CvmFre(_CvmCompanyDocs):
    """Parsed to staging `document` and `capital_social` (`ingest/cvm_fre.py`): share counts 2010-."""

    source_id: ClassVar[str] = "cvm_fre"
    version: ClassVar[str] = "1"
    KINDS: ClassVar[dict[str, int]] = {"FRE": 2010}
    contracts: ClassVar[dict[str, Any]] = cvm_fre.CONTRACTS
    dedup_staging: ClassVar[bool] = True

    def parse(self, blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
        return cvm_fre.parse_payload(blob, row)


class CvmVlmo(_CvmCompanyDocs):
    """Parsed to staging `document` and `movement` (`ingest/cvm_vlmo.py`): insider trades and holdings by role
    group, 2018-."""

    source_id: ClassVar[str] = "cvm_vlmo"
    version: ClassVar[str] = "1"
    KINDS: ClassVar[dict[str, int]] = {"VLMO": 2018}
    contracts: ClassVar[dict[str, Any]] = cvm_vlmo.CONTRACTS
    dedup_staging: ClassVar[bool] = True

    def parse(self, blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
        return cvm_vlmo.parse_payload(blob, row)


class CvmIpe(_CvmCompanyDocs):
    """Parsed to staging `document` (`ingest/cvm_ipe.py`): the evidence that proves corporate events."""

    source_id: ClassVar[str] = "cvm_ipe"
    version: ClassVar[str] = "1"
    KINDS: ClassVar[dict[str, int]] = {"IPE": 2003}
    contracts: ClassVar[dict[str, Any]] = cvm_ipe.CONTRACTS
    dedup_staging: ClassVar[bool] = True

    def parse(self, blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
        return cvm_ipe.parse_payload(blob, row)
