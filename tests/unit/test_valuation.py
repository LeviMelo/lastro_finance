"""`valuation(d)`: market cap from outstanding shares x the close, trailing earnings and controlling book value,
each as known on `d` (ADR-0021)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import duckdb
import polars as pl

from fin.catalog import build
from fin.config import Zones
from fin.store.tables import write_parquet

CNPJ = "11.111.111/0001-11"
NI = "Atribuído a Sócios da Empresa Controladora"
DIGITS = "11111111000111"


def _line(form: str, ref: str, statement: str, name: str, start: str | None, end: str, value: str) -> dict:
    return {
        "form": form, "cnpj": CNPJ, "reference_date": date.fromisoformat(ref), "version": 1, "company_name": "ACME",
        "cd_cvm": "000001", "statement": statement, "consolidation": "con", "statement_group": "x", "currency": "REAL",
        "scale": "UNIDADE", "period_order": "ÚLTIMO", "period_start": date.fromisoformat(start) if start else None,
        "period_end": date.fromisoformat(end), "equity_column": None, "account_code": "3.11.01" if statement == "DRE"
        else "2.03", "account_name": name, "value": Decimal(value), "fixed_account": True, "raw_sha256": "a",
        "raw_locator": "x", "ingest_run_id": "r",
    }  # fmt: skip


def test_valuation_point_in_time(zones: Zones) -> None:
    c, s = zones.core, zones.staging
    write_parquet(
        pl.DataFrame(
            {
                "issuer_id": ["C1"],
                "cnpj": [DIGITS],
                "trade_name": ["ACME"],
                "legal_name": ["ACME SA"],
                "sector": ["Varejo"],
            }
        ),
        c / "issuer" / "issuer.parquet",
    )
    write_parquet(
        pl.DataFrame(
            {
                "issuer_id": ["C1"],
                "instrument_id": ["I1"],
                "root": ["ACME"],
                "vt_from": [date(2020, 1, 2)],
                "vt_to": [date(2025, 12, 30)],
                "method": ["b3_root"],
            }
        ),
        c / "issuer_instrument" / "issuer_instrument.parquet",
    )
    write_parquet(
        pl.DataFrame({"instrument_id": ["I1"], "asset_class": ["share"], "especi": ["ON NM"]}),
        c / "instrument" / "instrument.parquet",
    )
    write_parquet(
        pl.DataFrame(
            {
                "instrument_id": ["I1", "I1"],
                "trade_date": [date(2025, 9, 1), date(2025, 9, 2)],
                "market_segment": ["lote_padrao"] * 2,
                "ticker": ["ACME3"] * 2,
                "close": [Decimal("9"), Decimal("10")],
                "volume": [Decimal("1"), Decimal("1")],
                "brl_num": [1, 1],
                "brl_den": [1, 1],
            }
        ),
        c / "price_daily" / "year=2025.parquet",
    )
    sc = {
        "issuer_cnpj": [DIGITS] * 2,
        "form": ["itr"] * 2,
        "reference_date": [date(2025, 6, 30), date(2025, 9, 30)],
        "version": [1, 1],
        "received_on": [date(2025, 8, 10), date(2025, 11, 10)],
        "unit": [1, 1],
        "common": [1100, 9999],
        "preferred": [0, 0],
        "common_treasury": [100, 0],
        "preferred_treasury": [0, 0],
    }  # fmt: skip  -- the 2025-09-30 filing is received after `d`: not used
    write_parquet(pl.DataFrame(sc), c / "share_count" / "share_count.parquet")
    fac = {  # a 11:10 bonus after the 2025-06-30 count grows it; one before the count is already in it
        "instrument_id": ["I1", "I1"], "ex_date": [date(2025, 1, 10), date(2025, 7, 15)],
        "split_factor": [0.5, 10 / 11], "cash_factor": [1.0, 1.0],
    }  # fmt: skip
    write_parquet(pl.DataFrame(fac), zones.derived / "adjustment_factor" / "adjustment_factor.parquet")
    lines = [
        _line("dfp", "2024-12-31", "DRE", NI, "2024-01-01", "2024-12-31", "500"),
        _line("itr", "2024-06-30", "DRE", NI, "2024-01-01", "2024-06-30", "200"),
        _line("itr", "2025-06-30", "DRE", NI, "2025-01-01", "2025-06-30", "300"),
        _line("itr", "2025-06-30", "BPP", "Patrimônio Líquido Consolidado", None, "2025-06-30", "5000"),
        _line("itr", "2025-06-30", "BPP", "Participação dos Acionistas Não Controladores", None, "2025-06-30", "1000"),
    ]  # fmt: skip
    write_parquet(pl.DataFrame(lines), s / "cvm_dfp_itr" / "statement_line" / "a.parquet")
    docs = pl.DataFrame(
        {
            "form": ["dfp", "itr", "itr"],
            "cnpj": [CNPJ] * 3,
            "reference_date": [date(2024, 12, 31), date(2024, 6, 30), date(2025, 6, 30)],
            "version": [1, 1, 1],
            "received_on": [date(2025, 3, 1), date(2024, 8, 10), date(2025, 8, 10)],
        }
    )
    write_parquet(docs, s / "cvm_dfp_itr" / "document" / "a.parquet")
    assert "valuation()" in build(zones)
    con = duckdb.connect(str(zones.catalog), read_only=True)
    cap, ttm, book, pe, pb = con.execute(
        "select market_cap_brl, earnings_ttm, book_value, price_earnings, price_book from valuation('2025-09-05')"
    ).fetchall()[0]
    # (1,100 - 100) x 11/10 x 10; 300 + 500 - 200; 5,000 - 1,000
    assert abs(cap - 11000) < 1e-6 and (ttm, book) == (600, 4000)
    assert abs(pe - 11000 / 600) < 1e-9 and abs(pb - 2.75) < 1e-12


def test_restated_statement_is_used_only_from_its_delivery(zones: Zones) -> None:
    """A version 2 of the 2024 DFP (net income restated from 500 to 800) received on 2025-09-20: on 2025-09-15 the
    trailing earnings use version 1 (300 + 500 - 200), on 2025-09-25 the restatement (300 + 800 - 200)."""
    test_valuation_point_in_time(zones)
    s = zones.staging
    v2 = _line("dfp", "2024-12-31", "DRE", NI, "2024-01-01", "2024-12-31", "800") | {"version": 2}
    write_parquet(pl.DataFrame([v2]), s / "cvm_dfp_itr" / "statement_line" / "b.parquet")
    doc = {"form": ["dfp"], "cnpj": [CNPJ], "reference_date": [date(2024, 12, 31)], "version": [2],
           "received_on": [date(2025, 9, 20)]}  # fmt: skip
    write_parquet(pl.DataFrame(doc), s / "cvm_dfp_itr" / "document" / "b.parquet")
    build(zones)
    con = duckdb.connect(str(zones.catalog), read_only=True)
    q = "select earnings_ttm from valuation(?)"
    assert con.execute(q, [date(2025, 9, 15)]).fetchone()[0] == 600
    assert con.execute(q, [date(2025, 9, 25)]).fetchone()[0] == 900
