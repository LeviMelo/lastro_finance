"""Findings: the VNA rule catches a month that departs from IBGE's index; ids are stable; resolutions apply."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import polars as pl

from fin.config import Zones
from fin.quality import findings
from fin.store.tables import write_parquet


def _obs(series: str, ref: str, value: str) -> dict[str, object]:
    return {"series_id": series, "vt_reference": ref, "value": Decimal(value)}


def test_vna_rule_and_stable_ids(zones: Zones, tmp_path: Path) -> None:
    rows = [
        _obs("ibge_sidra:1737/v2266", "2013-12", "3815.39"),
        _obs("ibge_sidra:1737/v2266", "2014-01", "3836.37"),
        _obs("tesouro_vna:NTN-B", "2014-01-15", "2363.026594"),  # = trunc(1000 x 3815.39 / 1614.62): no finding
        _obs("tesouro_vna:NTN-B", "2014-02-15", "2376.026557"),  # Tesouro's published value: implies 3836.38
    ]
    df = pl.DataFrame(rows, schema={"series_id": pl.String, "vt_reference": pl.String, "value": pl.Decimal(38, 24)})
    write_parquet(df, zones.core / "series_observation" / "a.parquet")
    out = findings.vna_ntnb_vs_ipca(zones)
    assert out["vt"].to_list() == [date(2014, 2, 15)]
    assert out["expected"][0] == "2376.020363" and "3836.3800" in out["detail"][0]

    res = tmp_path / "resolutions.toml"
    fid = findings.finding_id("vna_ntnb_vs_ipca", "tesouro_vna:NTN-B", date(2014, 2, 15))
    res.write_text(f'[{fid}]\nstatus = "acknowledged"\nnote = "kept as published"\n', encoding="utf-8")
    assert findings.run(zones, only=["vna_ntnb_vs_ipca"], resolutions_path=res) == {"vna_ntnb_vs_ipca": 1}
    got = pl.read_parquet(zones.quality / "dq_finding" / "vna_ntnb_vs_ipca.parquet")
    assert got.select("finding_id", "status").rows() == [(fid, "acknowledged")]


def test_ohlc_zero_price_is_an_error(zones: Zones) -> None:
    p = pl.DataFrame(
        {
            "instrument_id": ["I1", "I1"],
            "ticker": ["BGIP4"] * 2,
            "trade_date": [date(2021, 5, 17), date(2021, 5, 18)],
            "market_segment": ["lote_padrao"] * 2,
            **{k: [Decimal("22.1"), Decimal("0")] for k in ("open", "high", "low", "close")},
            "raw_locator": ["a", "b"],
        }
    )
    write_parquet(p, zones.core / "price_daily" / "year=2021.parquet")
    out = findings.ohlc_inconsistent(zones)
    assert out.select("vt", "severity").rows() == [(date(2021, 5, 18), "error")]
