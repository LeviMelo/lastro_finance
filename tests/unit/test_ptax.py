"""PTAX: exact decimals, every bulletin kept, the closing PTAX as series, one request per listed currency."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import polars as pl

from fin.ingest import ptax, series
from fin.ingest.base import Mode

FIX = Path(__file__).parents[1] / "fixtures" / "bcb_ptax"


def _row(dataset_id: str) -> dict[str, Any]:
    return {
        "raw_sha256": "a" * 64,
        "ingest_run_id": "r",
        "dataset_id": dataset_id,
        "fetched_at": datetime(2026, 11, 7, 12, 0),
    }


def _quotes(name: str, dataset_id: str) -> pl.DataFrame:
    df = ptax.parse_quotes((FIX / name).read_bytes(), _row(dataset_id))
    good, bad = ptax.QUOTE.split(df)
    assert bad.height == 0
    return good


def test_every_bulletin_is_kept_with_exact_rates() -> None:
    q = _quotes("CotacaoMoedaPeriodo_USD_1999-10-27_1999-10-27.json", "period_USD")
    assert q.height == 18
    assert set(q["bulletin"]) == {"Abertura", "Intermediário", "Fechamento", "Fechamento Interbancário"}
    close = q.filter(pl.col("bulletin") == "Fechamento").row(0, named=True)
    assert close["brl_buy"] == Decimal("1.9946") and close["brl_sell"] == Decimal("1.9954")
    assert close["quoted_at"] == datetime(1999, 10, 27, 21, 29)


def test_yen_is_quoted_in_brl_per_unit_with_parity_per_usd() -> None:
    q = _quotes("CotacaoMoedaPeriodo_JPY_2024-12-30_2024-12-31.json", "period_JPY")
    last = q.row(q.height - 1, named=True)
    assert last["bulletin"] == "Fechamento" and last["quote_date"] == date(2024, 12, 31)
    assert last["brl_sell"] == Decimal("0.03947") and last["parity_sell"] == Decimal("156.89")


def test_dolar_endpoint_is_the_closing_bulletin_without_parity() -> None:
    q = _quotes("CotacaoDolarPeriodo_2024-01-02_2024-01-05.json", "dolar_period")
    assert q.height == 4 and set(q["bulletin"]) == {"Fechamento"} and q["parity_buy"].null_count() == 4
    assert q["brl_sell"][0] == Decimal("4.89160")


def test_pre_real_values_are_published_not_rebased() -> None:
    q = _quotes("CotacaoDolarPeriodo_1984-11-28_1985-01-31_top3.json", "dolar_period")
    assert q["brl_buy"][0] == Decimal("2814.0")


def test_series_take_the_closing_ptax_and_the_later_of_two_rows() -> None:
    row = _row("period_USD")
    blob = (FIX / "CotacaoMoedaPeriodo_USD_2025-04-23_2025-04-23.json").read_bytes()
    parsed = {p.dataset_id: p.frame for p in ptax.parse_payload(blob, row)}
    obs, defs = parsed["observation"], parsed["definition"]
    assert set(obs["series_id"]) == {"bcb_ptax:USD:buy", "bcb_ptax:USD:sell"} and obs.height == 2
    assert series.OBSERVATION.split(obs)[1].height == 0 and series.DEFINITION.split(defs)[1].height == 0
    assert set(defs["unit"]) == {"BRL per 1 USD, as published (not rebased across currency changes)"}
    sell = obs.filter(pl.col("series_id") == "bcb_ptax:USD:sell").row(0, named=True)
    assert sell["value"] == Decimal("5.688") and sell["raw_locator"] == "$.value[5]"


def test_usd_close_2024_12_31() -> None:
    blob = (FIX / "CotacaoMoedaPeriodo_JPY_2024-12-30_2024-12-31.json").read_bytes()
    obs = {p.dataset_id: p.frame for p in ptax.parse_payload(blob, _row("period_JPY"))}["observation"]
    sell = obs.filter((pl.col("series_id") == "bcb_ptax:JPY:sell") & (pl.col("vt_date") == date(2024, 12, 31)))
    assert sell["value"].to_list() == [Decimal("0.03947")]


def test_currency_list() -> None:
    (p,) = ptax.parse_payload((FIX / "Moedas.json").read_bytes(), _row("moedas"))
    good, bad = ptax.CURRENCY.split(p.frame)
    assert bad.height == 0 and good.height == 10
    assert dict(zip(good["symbol"], good["quote_type"], strict=True))["EUR"] == "B"


def test_follow_asks_for_every_listed_currency() -> None:
    c = ptax.BcbPtax()
    (spec,) = c.discover(Mode.BACKFILL, None)  # type: ignore[arg-type]
    specs = list(c.follow(spec, (FIX / "Moedas.json").read_bytes()))
    assert len(specs) == 10 and specs[0].dataset_id == "period_AUD"
    params = specs[0].params or {}
    assert params["@moeda"] == "'AUD'" and params["@dataInicial"] == "'01-01-1984'"
