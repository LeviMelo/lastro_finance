"""Archive-first connectors for ephemeral sources (PLAN §4.1 invariant 13).

Each of these sources serves only "today" or a short rolling window, measured in recon on 2026-11-07:

| source | what is served | note |
|---|---|---|
| `cvm_cia_cadastro` | the current company registry, rebuilt daily | docs/sources/cvm_cia_cadastro.md |
| `cvm_fi_cadastro` | the current fund/class/subclass registries | docs/sources/cvm_fi_cadastro.md |
| `anbima_titulos_publicos` | the last ~6 business days of bond rates | docs/sources/anbima_titulos_publicos.md |
| `b3_bdi` | the last 21 business days of the BDI tables (settlements…) | docs/sources/b3_settlement_prices.md |

They archive now and parse later: a parser is written only against a layout confirmed on a real file (PLAN §4.13),
and every day archived meanwhile is parsed then, from raw.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from typing import Any, ClassVar
from zoneinfo import ZoneInfo

import polars as pl

from fin.config import Zones
from fin.ingest import tesouro
from fin.ingest.base import Connector, Mode, Parsed
from fin.ingest.fetch import FetchSpec
from fin.ingest.http import BROWSER_UA
from fin.reference.calendar import Calendar
from fin.schema import Contract
from fin.store.manifest import Manifest

BRT = ZoneInfo("America/Sao_Paulo")
MONTHS_PT = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")


def today_brt() -> date:
    return datetime.now(BRT).date()


def _calendar(zones: Zones) -> Calendar:
    from fin.ingest.anbima_calendar import load_calendar

    return Calendar.from_frame(load_calendar(zones))


def _archived_dates(zones: Zones, source_id: str, dataset_id: str) -> set[date]:
    m = Manifest(zones.manifest).read()
    m = m.filter(
        (pl.col("source_id") == source_id)
        & (pl.col("dataset_id") == dataset_id)
        & (pl.col("http_status") == 200)
        & pl.col("source_reference_date").is_not_null()
    )
    return set(m["source_reference_date"].to_list())


class CvmCiaCadastro(Connector):
    source_id: ClassVar[str] = "cvm_cia_cadastro"
    version: ClassVar[str] = "0-archive"
    BASE = "https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD"

    def discover(self, mode: Mode, zones: Zones, **options: Any) -> Iterable[FetchSpec]:
        d = today_brt()
        yield FetchSpec(
            self.source_id, "cad_cia_aberta", f"{self.BASE}/DADOS/cad_cia_aberta.csv", "csv", reference_date=d
        )
        yield FetchSpec(self.source_id, "meta_cad_cia_aberta", f"{self.BASE}/META/meta_cad_cia_aberta.txt", "txt")


class CvmFiCadastro(Connector):
    source_id: ClassVar[str] = "cvm_fi_cadastro"
    version: ClassVar[str] = "0-archive"
    BASE = "https://dados.cvm.gov.br/dados/FI/CAD"

    def discover(self, mode: Mode, zones: Zones, **options: Any) -> Iterable[FetchSpec]:
        d = today_brt()
        for dataset, name, ext in (
            ("cad_fi", "DADOS/cad_fi.csv", "csv"),
            ("cad_fi_hist", "DADOS/cad_fi_hist.zip", "zip"),
            ("registro_fundo_classe", "DADOS/registro_fundo_classe.zip", "zip"),
            ("meta_cad_fi", "META/meta_cad_fi.zip", "zip"),
            ("meta_registro_fundo_classe", "META/meta_registro_fundo_classe.zip", "zip"),
        ):
            ref = d if dataset.startswith(("cad_fi", "registro")) else None
            yield FetchSpec(self.source_id, dataset, f"{self.BASE}/{name}", ext, reference_date=ref)


class AnbimaTitulosPublicos(Connector):
    """Fetch every business day of the last two weeks: the served window (~6 business days) is caught whole each
    day, so ANBIMA's in-place corrections become new raw versions. A 404 is a day outside the window."""

    source_id: ClassVar[str] = "anbima_titulos_publicos"
    version: ClassVar[str] = "0-archive"
    BASE = "https://www.anbima.com.br/informacoes/merc-sec/arqs"
    LOOKBACK_BUSINESS_DAYS = 10

    def discover(self, mode: Mode, zones: Zones, **options: Any) -> Iterable[FetchSpec]:
        cal = _calendar(zones)
        end = cal.preceding(today_brt())
        start = cal.add_business_days(end, -self.LOOKBACK_BUSINESS_DAYS)
        for d in reversed(cal.business_days(start, end)):
            yield FetchSpec(
                self.source_id,
                "ms_txt",
                f"{self.BASE}/ms{d:%y%m%d}.txt",
                "txt",
                reference_date=d,
                absent_status=frozenset({404}),
            )
            yield FetchSpec(
                self.source_id,
                "ms_xls",
                f"{self.BASE}/m{d:%y}{MONTHS_PT[d.month - 1]}{d:%d}.xls",
                "xls",
                reference_date=d,
                absent_status=frozenset({404}),
            )


class _AnbimaWindow(Connector):
    """ANBIMA's free forms serve the last 6 business days, enforced server-side (docs/sources/anbima_ettj.md,
    anbima_vna.md, anbima_debentures.md). Each run asks for the last 10 business days, so the whole window is caught
    and in-place corrections become new raw versions; out-of-window dates answer 404 or a short stub (absent)."""

    version: ClassVar[str] = "0-archive"
    user_agent: ClassVar[str | None] = BROWSER_UA
    LOOKBACK_BUSINESS_DAYS = 10

    def days(self, zones: Zones) -> list[date]:
        cal = _calendar(zones)
        end = cal.preceding(today_brt())
        return list(reversed(cal.business_days(cal.add_business_days(end, -self.LOOKBACK_BUSINESS_DAYS), end)))


class AnbimaEttj(_AnbimaWindow):
    source_id: ClassVar[str] = "anbima_ettj"
    FORM = "https://www.anbima.com.br/informacoes/est-termo/"

    def discover(self, mode: Mode, zones: Zones, **options: Any) -> Iterable[FetchSpec]:
        for d in self.days(zones):
            yield FetchSpec(
                self.source_id,
                "curva_zero_txt",
                f"{self.FORM}CZ-down.asp",
                "txt",
                method="POST",
                data={
                    "escolha": "2",
                    "Idioma": "PT",
                    "saida": "txt",
                    "Dt_Ref": f"{d:%d/%m/%Y}",
                    "Dt_Ref_Ver": f"{d:%Y%m%d}",
                },
                headers={"Referer": self.FORM},
                reference_date=d,
                conditional=False,
                min_bytes=500,
                absent_status=frozenset({404}),
            )


class AnbimaVna(_AnbimaWindow):
    source_id: ClassVar[str] = "anbima_vna"
    FORM = "https://www.anbima.com.br/informacoes/vna/"

    def discover(self, mode: Mode, zones: Zones, **options: Any) -> Iterable[FetchSpec]:
        for d in self.days(zones):
            yield FetchSpec(
                self.source_id,
                "vna_txt",
                f"{self.FORM}vna-down.asp",
                "txt",
                method="POST",
                data={
                    "escolha": "2",
                    "Idioma": "PT",
                    "saida": "txt",
                    "Data": f"{d:%d%m%Y}",
                    "Inicio": f"{d:%d/%m/%Y}",
                    "Dt_Ref_Ver": f"{d:%Y%m%d}",
                },
                headers={"Referer": self.FORM},
                reference_date=d,
                conditional=False,
                min_bytes=200,
                absent_status=frozenset({404}),
            )


class AnbimaDebentures(_AnbimaWindow):
    source_id: ClassVar[str] = "anbima_debentures"
    BASE = "https://www.anbima.com.br/informacoes/merc-sec-debentures/arqs"

    def discover(self, mode: Mode, zones: Zones, **options: Any) -> Iterable[FetchSpec]:
        for d in self.days(zones):
            yield FetchSpec(
                self.source_id,
                "db_txt",
                f"{self.BASE}/db{d:%y%m%d}.txt",
                "txt",
                reference_date=d,
                absent_status=frozenset({404}),
            )


class AnbimaIndicadores(Connector):
    """The 'Quadro Indicadores' page: the only free carrier found of IGP-M index numbers and of ANBIMA's IPCA/IGP-M
    projections, latest values only (docs/sources/anbima_projecoes.md). Archived daily as HTML."""

    source_id: ClassVar[str] = "anbima_projecoes"
    version: ClassVar[str] = "0-archive"
    user_agent: ClassVar[str | None] = BROWSER_UA

    def discover(self, mode: Mode, zones: Zones, **options: Any) -> Iterable[FetchSpec]:
        yield FetchSpec(
            self.source_id,
            "quadro_indicadores",
            "https://www.anbima.com.br/informacoes/indicadores/",
            "html",
            reference_date=today_brt(),
            conditional=False,
        )


class TesouroPrecoTaxa(Connector):
    """Tesouro Direto prices and rates since 2004-12-31, one CSV replaced in full every morning
    (docs/sources/tesouro_transparente.md). Not ephemeral, but each replacement is a version (a correction of the
    past would otherwise be invisible); conditional GET makes an unchanged day a 304."""

    source_id: ClassVar[str] = "tesouro_transparente"
    version: ClassVar[str] = "1"
    contracts: ClassVar[dict[str, Contract]] = {"price_rate": tesouro.PRICE_RATE}
    dedup_staging: ClassVar[bool] = True  # the whole history, re-sent every morning

    def parse(self, blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
        return tesouro.parse_payload(blob, row)

    def derive(self, zones: Zones, run: Any) -> None:
        from fin.core import tesouro as core_tesouro

        core_tesouro.build(zones, run)

    URL = (
        "https://www.tesourotransparente.gov.br/ckan/dataset/df56aa42-484a-4a59-8184-7676580c81e3/resource/"
        "796d2059-14e9-44e3-80c9-2d9e30b405c1/download/precotaxatesourodireto.csv"
    )

    def discover(self, mode: Mode, zones: Zones, **options: Any) -> Iterable[FetchSpec]:
        yield FetchSpec(self.source_id, "preco_taxa", self.URL, "csv", reference_date=today_brt())


class NefinFactors(Connector):
    """NEFIN-USP Brazilian risk factors, daily and monthly CSVs, rewritten in place (docs/sources/nefin.md)."""

    source_id: ClassVar[str] = "nefin"
    version: ClassVar[str] = "0-archive"
    BASE = "https://nefin.com.br/nefindata/risk-factors"

    def discover(self, mode: Mode, zones: Zones, **options: Any) -> Iterable[FetchSpec]:
        for name in (
            "nefin_factors",
            "nefin_factors_equally_weighted",
            "nefin_factors_monthly",
            "nefin_factors_equally_weighted_monthly",
        ):
            yield FetchSpec(self.source_id, name, f"{self.BASE}/{name}.csv", "csv")


class B3Files(Connector):
    """B3's consolidated daily files on arquivos.b3.com.br (docs/sources/b3_instruments.md):
    `GET /api/download/requestname?fileName=<F>&date=YYYY-MM-DD` gives a one-time token, `GET /api/download/?token=`
    the CSV. Served since 2025-06-10 only (measured 2026-11-07; fixed start or rolling window not yet known), so the
    whole served history is backfilled and every new day archived. A weekend has no token; a B3 holiday has a token
    and an empty body (absent). The token responses are archived like any other payload."""

    source_id: ClassVar[str] = "b3_instruments"
    version: ClassVar[str] = "0-archive"
    user_agent: ClassVar[str | None] = BROWSER_UA
    BASE = "https://arquivos.b3.com.br/api/download"
    FILES: ClassVar[tuple[str, ...]] = ("InstrumentsConsolidatedFile", "TradeInformationConsolidatedFile")
    FIRST_SERVED = date(2025, 6, 10)
    LOOKBACK_BUSINESS_DAYS = 10

    def discover(self, mode: Mode, zones: Zones, **options: Any) -> Iterable[FetchSpec]:
        cal = _calendar(zones)
        end = cal.preceding(today_brt())
        start = self.FIRST_SERVED if mode is Mode.BACKFILL else cal.add_business_days(end, -self.LOOKBACK_BUSINESS_DAYS)
        for name in self.FILES:
            have = _archived_dates(zones, self.source_id, name)
            for d in reversed(cal.business_days(start, end)):
                if d in have:
                    continue
                yield FetchSpec(
                    self.source_id,
                    f"{name}.token",
                    f"{self.BASE}/requestname",
                    "json",
                    params={"fileName": name, "date": f"{d:%Y-%m-%d}"},
                    reference_date=d,
                    conditional=False,
                    min_bytes=10,
                    locator=name,
                    # TradeInformationConsolidatedFile answers 400 for business days without a B3 session
                    # (2025-12-24 and 2025-12-31, measured 2026-11-07; the instruments file is header-only then).
                    absent_status=frozenset({400}),
                )

    def follow(self, spec: FetchSpec, blob: bytes) -> Iterable[FetchSpec]:
        if not spec.dataset_id.endswith(".token"):
            return ()
        token = json.loads(blob).get("token")
        if not token:
            return ()
        return [
            FetchSpec(
                self.source_id,
                spec.dataset_id.removesuffix(".token"),
                f"{self.BASE}/",
                "csv",
                params={"token": token},
                reference_date=spec.reference_date,
                conditional=False,
                min_bytes=100,
                notes="token request: see the .token dataset row of the same reference date",
            )
        ]


class B3PesquisaPregao(Connector):
    """B3's per-session downloads `www.b3.com.br/pesquisapregao/download?filelist=<NAME>,` (docs/sources/
    b3_settlement_prices.md, b3_reference_rates.md). Long history, so not ephemeral, but archived daily as it is
    published:
    - `PR<YYMMDD>.zip`: BVBG.086 price reports (settlements `AdjstdQt`, open interest `OpnIntrst`), since 2018-01-02;
    - `TS<YYMMDD>.ex_`: TaxaSwap.txt, every B3 reference curve (PRE, DIC…), since 2000-01-14. The `.ex_` is a PKSFX
      self-extracting EXE: it is stored as bytes and read as a zip, never executed.
    A day without a file answers HTTP 200 with a 22-byte empty zip (absent). Backfill takes `--years`."""

    source_id: ClassVar[str] = "b3_pesquisapregao"
    version: ClassVar[str] = "0-archive"
    user_agent: ClassVar[str | None] = BROWSER_UA
    URL = "https://www.b3.com.br/pesquisapregao/download"
    FAMILIES: ClassVar[dict[str, tuple[str, str, date]]] = {
        # dataset: (file pattern, raw ext, first served)
        "PR": ("PR{d:%y%m%d}.zip", "zip", date(2018, 1, 2)),
        "TS": ("TS{d:%y%m%d}.ex_", "exe", date(2000, 1, 14)),
    }
    LOOKBACK_BUSINESS_DAYS = 10

    def discover(self, mode: Mode, zones: Zones, **options: Any) -> Iterable[FetchSpec]:
        cal = _calendar(zones)
        end = cal.preceding(today_brt())
        families = list(options.get("families") or self.FAMILIES)
        years: list[int] | None = options.get("years")
        for fam in families:
            pattern, ext, first = self.FAMILIES[fam]
            have = _archived_dates(zones, self.source_id, fam)
            if mode is Mode.BACKFILL:
                lo = max(first, date(min(years), 1, 1)) if years else first
                hi = min(end, date(max(years), 12, 31)) if years else end
                lo = max(lo, cal.first)
                if lo > hi:
                    continue
                days = cal.business_days(lo, hi)
            else:
                days = cal.business_days(cal.add_business_days(end, -self.LOOKBACK_BUSINESS_DAYS), end)
            for d in reversed(days):
                if d in have:
                    continue
                name = pattern.format(d=d)
                yield FetchSpec(
                    self.source_id,
                    fam,
                    self.URL,
                    ext,
                    params={"filelist": f"{name},"},
                    reference_date=d,
                    conditional=False,
                    min_bytes=100,
                    locator=f"file={name}",
                )


class B3IndexPortfolio(Connector):
    """Index compositions from B3's index pages backend (docs/sources/b3_index_portfolio.md): today's portfolio, the
    quadrimestral theoretical portfolio and the preview. **No date parameter exists: only the current composition is
    served**, so each day not archived is lost. Index levels have deep history elsewhere and are not fetched here."""

    source_id: ClassVar[str] = "b3_index_portfolio"
    version: ClassVar[str] = "0-archive"
    user_agent: ClassVar[str | None] = BROWSER_UA
    BASE = "https://sistemaswebb3-listados.b3.com.br/indexProxy/indexCall"
    INDICES: ClassVar[tuple[str, ...]] = (
        "IBOV",
        "IBXX",
        "IBXL",
        "SMLL",
        "IFIX",
        "IDIV",
        "MLCX",
        "IFNC",
        "ICON",
        "IEEX",
        "IMOB",
        "ISEE",
        "ICO2",
        "UTIL",
    )

    @staticmethod
    def _b64(payload: dict[str, Any]) -> str:
        import base64

        return base64.b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()

    def discover(self, mode: Mode, zones: Zones, **options: Any) -> Iterable[FetchSpec]:
        d = today_brt()
        for idx in self.INDICES:
            page = {"language": "pt-br", "pageNumber": 1, "pageSize": 120, "index": idx, "segment": "1"}
            for endpoint, payload in (
                ("GetPortfolioDay", page),
                ("GetTheoricalPortfolio", page),
                ("GetDownloadPreview", {"index": idx, "language": "pt-br"}),
            ):
                yield FetchSpec(
                    self.source_id,
                    endpoint,
                    f"{self.BASE}/{endpoint}/{self._b64(payload)}",
                    "json",
                    reference_date=d,
                    conditional=False,
                    min_bytes=3,
                    locator=f"index={idx}",
                )


class B3IndexLevels(Connector):
    """Daily closing levels of B3's indices, one calendar year per request (indexStatisticsProxy GetPortfolioDay,
    a month x day grid with pt-BR numbers; docs/sources/context_br.md §8a). Backfill takes every year from the
    first one served; the daily job re-requests the current year."""

    source_id: ClassVar[str] = "b3_index_levels"
    version: ClassVar[str] = "0-archive"
    user_agent: ClassVar[str | None] = BROWSER_UA
    BASE = "https://sistemaswebb3-listados.b3.com.br/indexStatisticsProxy/IndexCall/GetPortfolioDay"
    FIRST_YEAR: ClassVar[dict[str, int]] = {  # first year with data (measured 2026-11-07)
        "IBOV": 1968, "IBXX": 1994, "IBXL": 1997, "SMLL": 2005, "MLCX": 2005, "IDIV": 2005, "IFIX": 2010,
        "IFNC": 2004, "ICON": 2006, "IEEX": 1994, "IMOB": 2007, "IMAT": 2005, "INDX": 1999, "UTIL": 2005,
        "ISEE": 2005, "ICO2": 2010, "IGCX": 2001, "ITAG": 2002, "IGNM": 2006, "IGCT": 2005, "IVBX2": 1999,
        "BDRX": 2010, "IBRA": 2005,
    }  # fmt: skip

    def discover(self, mode: Mode, zones: Zones, **options: Any) -> Iterable[FetchSpec]:
        today = today_brt()
        rows = held_rows(zones, self.source_id, "index_levels")
        held = set(rows["notes"].to_list()) if rows.height else set()
        for idx, first in self.FIRST_YEAR.items():
            years = range(first, today.year + 1) if mode is Mode.BACKFILL else [today.year]
            for year in years:
                if f"index={idx}|{year}" in held and year < today.year:
                    continue
                payload = {"index": idx, "language": "pt-br", "year": str(year)}
                yield FetchSpec(
                    self.source_id,
                    "index_levels",
                    f"{self.BASE}/{B3IndexPortfolio._b64(payload)}",  # pyright: ignore[reportPrivateUsage]
                    "json",
                    reference_date=date(year, 12, 31) if year < today.year else today,
                    conditional=False,
                    min_bytes=3,
                    locator=f"index={idx}|{year}",
                )


class B3Bdi(Connector):
    """B3's Boletim Diário (BDI) tables: POST /bdi/table/<Table>/<d>/<d>/<page>/<take>, body {}.

    Only 21 business days are served. Each day not yet archived is fetched page by page (take 1000; 5000 is refused
    with HTTP 400, measured 2026-11-07); the last 2 business days are re-fetched each run to catch late corrections.
    """

    source_id: ClassVar[str] = "b3_bdi"
    version: ClassVar[str] = "0-archive"
    user_agent: ClassVar[str | None] = BROWSER_UA  # B3 hosts sit behind Cloudflare (docs/sources/b3_cotahist.md)
    BASE = "https://arquivos.b3.com.br/bdi/table"
    TAKE = 1000
    WINDOW = 21
    REFRESH = 2
    # Settlements (also in PR files since 2018), and what has no long-history route found: equity open interest,
    # securities lending, debenture trades on Puma (docs/sources/b3_instruments.md §7).
    TABLES: ClassVar[tuple[str, ...]] = (
        "ConsolidatedTradesDerivatives",
        "OpenPositionsEquities",
        "BTBLendingOpenPosition",
        "BTBLoanBalance",
        "BTBTrade",
        "DebenturesBusiness",
        "SharesInvesVolum",  # investor-type flows, month-to-date (docs/sources/context_br.md §8b)
    )

    def _spec(self, table: str, d: date, page: int) -> FetchSpec:
        return FetchSpec(
            self.source_id,
            table,
            f"{self.BASE}/{table}/{d:%Y-%m-%d}/{d:%Y-%m-%d}/{page}/{self.TAKE}",
            "json",
            method="POST",
            json={},
            reference_date=d,
            conditional=False,
            locator=f"page={page}",
        )

    def discover(self, mode: Mode, zones: Zones, **options: Any) -> Iterable[FetchSpec]:
        cal = _calendar(zones)
        end = cal.preceding(today_brt() - timedelta(days=0))
        days = cal.business_days(cal.add_business_days(end, -(self.WINDOW - 1)), end)
        for table in self.TABLES:
            have = _archived_dates(zones, self.source_id, table)
            for d in reversed(days):
                if d in have and d < days[-self.REFRESH]:
                    continue
                yield self._spec(table, d, 1)

    def follow(self, spec: FetchSpec, blob: bytes) -> Iterable[FetchSpec]:
        if spec.locator != "page=1" or spec.reference_date is None:
            return ()
        pages = int(json.loads(blob).get("table", {}).get("pageCount") or 1)
        return [self._spec(spec.dataset_id, spec.reference_date, p) for p in range(2, pages + 1)]


def held_rows(zones: Zones, source_id: str, dataset_id: str) -> pl.DataFrame:
    m = Manifest(zones.manifest).read()
    if m.is_empty():
        return m
    return m.filter(
        (pl.col("source_id") == source_id) & (pl.col("dataset_id") == dataset_id) & (pl.col("http_status") == 200)
    )
