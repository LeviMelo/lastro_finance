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
from fin.ingest.base import Connector, Mode
from fin.ingest.fetch import FetchSpec
from fin.ingest.http import BROWSER_UA
from fin.reference.calendar import Calendar
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
    TABLES: ClassVar[tuple[str, ...]] = ("ConsolidatedTradesDerivatives",)

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
