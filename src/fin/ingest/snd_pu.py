"""SND "PU Histórico": the daily unit price (PU) of every debenture, from its issue (docs/sources/snd_pu_historico.md).

`GET https://www.debentures.com.br/exploreosnd/consultaadados/emissoesdedebentures/puhistorico_e.asp`
with `op_exc=False&ativo=<ticker>&dt_ini=<dd/mm/yyyy>&dt_fim=<dd/mm/yyyy>` (**day first**, unlike `precosdenegociacao`,
which reads month first). One Latin-1, CRLF, tab-separated file per debenture:

    PU Histórico - Gerado em 08/11/2026 01:40:34
    <blank>
    Data do PU, Ativo, Valor Nominal, Juros, Prêmio, Preço Unitário, Critério de Cálculo, Situação (tab-separated,
    with a trailing tab)
    31/12/2024<TAB>SABP12<TAB>1.052,678070<TAB>82,855032<TAB>-<TAB>1.135,533102<TAB>Padrão - SND<TAB>Reg.<TAB>
    ...
    <blank><blank>Valores expressos em reais.<CR LF>Os valores refletem a nossa interpretação da escritura ...

Newest first; `-` (with trailing blanks) is no value; a ticker without a PU answers 200 with the header only. The
PU is the issuer-contract accrual SND computes (par value + accrued remuneration), not a market price. The header
line is checked: any other layout raises (`LayoutError`).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar

import polars as pl

from fin.config import Zones
from fin.ingest.base import Connector, Mode, NotData, Parsed
from fin.ingest.fetch import FetchSpec
from fin.ingest.snapshots import today_brt
from fin.schema import Column, Contract, Rule
from fin.store.manifest import Manifest
from fin.store.raw import RawStore

MONEY = pl.Decimal(38, 12)
HEADER = (
    "Data do PU",
    "Ativo",
    "Valor Nominal",
    "Juros",
    "Prêmio",
    "Preço Unitário",
    "Critério de Cálculo",
    "Situação",
)
DATE_ROW = re.compile(r"^\d\d/\d\d/\d{4}\t")

DEBENTURE_PU = Contract(
    table="staging.snd_pu_historico.debenture_pu",
    version=1,
    description="Daily PU of a debenture as computed by SND from the issue deed (SND 'PU Histórico').",
    columns=(
        Column("ref_date", pl.Date, "Data do PU", "data do PU", "date", False),
        Column("ticker", pl.String, "Ativo: debenture code (B3/Cetip)", "código do ativo", "", False),
        Column("par_value_brl", MONEY, "Valor Nominal (current, after amortisations)", "valor nominal", "BRL"),
        Column("accrued_interest_brl", MONEY, "Juros accrued since the last payment", "juros", "BRL"),
        Column("premium_brl", MONEY, "Prêmio (premium paid on the date, not part of the PU)", "prêmio", "BRL"),
        Column(
            "pu_brl", MONEY, "Preço Unitário; null when SND published none (17,599 rows, 0.2%)", "preço unitário", "BRL"
        ),
        Column("calc_criterion", pl.String, "Critério de Cálculo (Padrão - SND, ...)", "critério de cálculo"),
        Column("situation", pl.String, "Situação at that date (Reg., Exc....)", "situação"),
    ),
    rules=(Rule("pu_positive", pl.col("pu_brl").is_null() | (pl.col("pu_brl") > 0)),),
    key=("ticker", "ref_date", "raw_sha256"),
)


class LayoutError(ValueError):
    pass


def _num(text: str) -> Decimal | None:
    t = text.strip()
    if t in ("", "-"):
        return None
    try:
        d = Decimal(t.replace(".", "").replace(",", "."))
    except InvalidOperation as e:
        raise LayoutError(f"not a number: {text!r}") from e
    exp = d.as_tuple().exponent
    if isinstance(exp, int) and exp < -12:
        raise LayoutError(f"more than 12 decimals: {text!r}")
    return d


def parse_pu(blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
    lines = blob.decode("latin-1").replace("\r\n", "\n").split("\n")
    if not lines or not lines[0].startswith("PU Histórico"):
        raise NotData("not a PU Histórico file")
    head = next((i for i, ln in enumerate(lines[:6]) if ln.startswith("Data do PU")), None)
    if head is None:
        raise LayoutError("no header line")
    cols = tuple(c for c in lines[head].split("\t") if c != "")
    if cols != HEADER:
        raise LayoutError(f"columns changed: {cols} != {HEADER}")
    out: list[dict[str, Any]] = []
    for i, ln in enumerate(lines[head + 1 :], start=head + 2):
        if not DATE_ROW.match(ln):
            if ln.strip() and not ln.startswith(("Valores expressos", "Os valores refletem")):
                raise LayoutError(f"line {i}: unexpected text {ln[:60]!r}")
            continue
        f = ln.split("\t")
        if len(f) != 9 or f[8] != "":
            raise LayoutError(f"line {i}: {len(f)} fields")
        out.append(
            {
                "ref_date": datetime.strptime(f[0], "%d/%m/%Y").date(),  # noqa: DTZ007 (a calendar date)
                "ticker": f[1].strip(),
                "par_value_brl": _num(f[2]),
                "accrued_interest_brl": _num(f[3]),
                "premium_brl": _num(f[4]),
                "pu_brl": _num(f[5]),
                "calc_criterion": f[6].strip() or None,
                "situation": f[7].strip() or None,
                "raw_locator": f"line={i}",
            }
        )
    schema = {c.name: c.dtype for c in DEBENTURE_PU.columns} | {"raw_locator": pl.String}
    df = pl.DataFrame(out, schema=schema, orient="row").with_columns(
        pl.lit(row["raw_sha256"]).alias("raw_sha256"), pl.lit(row["ingest_run_id"]).alias("ingest_run_id")
    )
    yield Parsed("debenture_pu", "all", df)


class SndPuHistorico(Connector):
    """Backfill: the whole history of every debenture of SND's register (the latest archived `caracteristicas`
    lists them, dead ones included), one request each, skipping those already held. Incremental: the last 60 days of
    each debenture still registered (run it weekly or monthly; the history is not ephemeral)."""

    source_id: ClassVar[str] = "snd_pu_historico"
    version: ClassVar[str] = "1"
    min_interval: ClassVar[float] = 0.4  # one answer takes ~2.3 s: latency, not rate, bounds the run
    concurrency: ClassVar[int] = 3
    dedup_staging: ClassVar[bool] = True  # a re-sent range repeats the rows already held
    contracts: ClassVar[dict[str, Contract]] = {"debenture_pu": DEBENTURE_PU}
    BASE = "https://www.debentures.com.br/exploreosnd/consultaadados/emissoesdedebentures/puhistorico_e.asp"
    FIRST = date(1980, 1, 1)  # SND's first issue is from 1981-08
    RECENT_DAYS = 60

    def _spec(self, ticker: str, a: date, b: date) -> FetchSpec:
        return FetchSpec(
            self.source_id,
            "pu",
            self.BASE,
            "txt",
            params={"op_exc": "False", "ativo": ticker, "dt_ini": f"{a:%d/%m/%Y}", "dt_fim": f"{b:%d/%m/%Y}"},
            reference_date=b,
            conditional=False,
            locator=f"ticker={ticker}",
        )

    @staticmethod
    def register(zones: Zones) -> list[tuple[str, bool]]:
        """(ticker, still registered) from the latest archived SND `caracteristicas`."""
        m = Manifest(zones.manifest).read()
        if m.is_empty():
            return []
        m = m.filter(
            (pl.col("source_id") == "snd_debentures")
            & (pl.col("dataset_id") == "caracteristicas")
            & (pl.col("http_status") == 200)
        )
        if m.is_empty():
            return []
        lines = RawStore(zones.raw).read(m.sort("fetched_at")["raw_sha256"][-1]).decode("latin-1").splitlines()
        head = next(i for i, ln in enumerate(lines) if ln.startswith("Codigo do Ativo"))
        cols = [c.strip() for c in lines[head].split("\t")]
        si = cols.index("Situacao")
        out: list[tuple[str, bool]] = []
        for ln in lines[head + 1 :]:
            f = ln.split("\t")
            if len(f) > si and f[0].strip():
                out.append((f[0].strip(), not f[si].strip().startswith("Exclu")))
        return out

    def discover(self, mode: Mode, zones: Zones, **options: Any) -> Iterable[FetchSpec]:
        today = today_brt()
        reg = self.register(zones)
        if mode is Mode.BACKFILL:
            m = Manifest(zones.manifest).read()
            held: set[str] = set()
            if not m.is_empty():
                h = m.filter(
                    (pl.col("source_id") == self.source_id)
                    & (pl.col("dataset_id") == "pu")
                    & (pl.col("http_status") == 200)
                )
                held = set(h["notes"].to_list())
            for t, _ in reg:
                if f"ticker={t}" not in held:
                    yield self._spec(t, self.FIRST, today)
        else:
            for t, active in reg:
                if active:
                    yield self._spec(t, today - timedelta(days=self.RECENT_DAYS), today)

    def parse(self, blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
        return parse_pu(blob, row)
