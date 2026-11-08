"""The dossier values each holding at its last close, with method and as-of date, and labels a missing one."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
from test_valuation import test_valuation_point_in_time  # pytest puts tests/unit on the path

from fin.catalog import build as build_catalog
from fin.config import Zones
from fin.export.dossier import build
from fin.store.tables import write_parquet


def test_dossier_values_holdings_and_labels_missing(zones: Zones, tmp_path: Path) -> None:
    test_valuation_point_in_time(zones)  # ACME3's prices (close 10 on 2025-09-02) and its valuation
    ids = {"instrument_id": ["I1"], "scheme": ["TICKER"], "value": ["ACME3"], "vt_from": [date(2020, 1, 2)],
           "vt_to": [date(2025, 12, 30)]}  # fmt: skip
    write_parquet(pl.DataFrame(ids), zones.core / "instrument_identifier" / "instrument_identifier.parquet")
    build_catalog(zones)
    pf = tmp_path / "p.toml"
    pf.write_text("[holdings]\nACME3 = 100\nNOPE3 = 5\n[performance]\nsince = 2025-09-01\n", encoding="utf-8")
    text = build(zones, pf, date(2025, 9, 5)).read_text(encoding="utf-8")
    assert "| ACME3 | 100 | R$ 10,00 (2025-09-02) | R$ 1.000,00 |" in text
    assert "NOPE3" in text and "sem preço" in text
    assert (zones.exports / "dossier-2025-09-05" / "holdings.parquet").exists()
