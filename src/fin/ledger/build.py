"""`fin ledger` / `fin tax`: run the ledger on a transactions file and write its tables to core `ledger/`.

The file is stored in raw first (content-addressed, invariant 1); every row written carries its SHA-256 and the
file line (or the corporate event) it came from (invariant 2). Rebuilding from the same file and core is identical.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from pathlib import Path

import polars as pl

from fin.config import Zones
from fin.ledger import sources
from fin.ledger.engine import LedgerResult, build_ledger
from fin.ledger.transactions import load
from fin.schema import Column, Contract
from fin.store.raw import RawStore
from fin.tax.engine import IncomeTax, MonthTax, assess, income_tax

DEFAULT_FILE = "inbox/transactions.csv"
Q = Decimal("0.00000001")
DEC = pl.Decimal(38, 8)


def _brl(name: str, en: str, pt: str) -> Column:
    return Column(name, DEC, en, pt, "BRL")


POSITION = Contract("ledger_position", 1, "position after each day it changed (average cost, all brokers)", (
    Column("date", pl.Date, "end of day", "data", "date", False),
    Column("ticker", pl.String, "ticker or Tesouro title", "ativo", nullable=False),
    Column("asset_class", pl.String, "tax class", "classe"),
    Column("quantity", DEC, "units held", "quantidade", "units"),
    _brl("cost_brl", "total cost (preço médio x quantity)", "custo total"),
))  # fmt: skip
REALIZED = Contract("ledger_realized", 1, "realized sales (swing, day trade, fixed income lots)", (
    Column("date", pl.Date, "sale date", "data", "date", False),
    Column("ticker", pl.String, "asset", "ativo", nullable=False),
    Column("asset_class", pl.String, "tax class", "classe"),
    Column("mode", pl.String, "swing, day or fixed_income", "modalidade"),
    Column("broker", pl.String, "broker", "corretora"),
    Column("quantity", DEC, "units sold", "quantidade", "units"),
    _brl("sale_value_brl", "quantity x price", "valor de alienação"),
    _brl("proceeds_brl", "net of fees", "valor líquido"),
    _brl("cost_brl", "average or lot cost", "custo"),
    _brl("result_brl", "proceeds - cost", "resultado"),
    _brl("irrf_brl", "IRRF reported (null: not reported)", "IRRF informado"),
    _brl("iof_brl", "IOF withheld (Tesouro)", "IOF"),
    _brl("ir_withheld_brl", "IR withheld at source (Tesouro)", "IR na fonte"),
))  # fmt: skip
INCOME = Contract("ledger_income", 1, "cash income: reported by the file or expected from corporate events", (
    Column("date", pl.Date, "payment date (data com when unknown)", "data", "date", False),
    Column("ticker", pl.String, "asset", "ativo"),
    Column("kind", pl.String, "DIVIDEND, JCP, INCOME, AMORTIZATION, COUPON, FEE", "tipo"),
    _brl("gross_brl", "gross amount", "valor bruto"),
    _brl("irrf_brl", "withheld", "IR retido"),
    Column("status", pl.String, "reported or expected", "situação"),
))  # fmt: skip
POSTING = Contract("ledger_posting", 1, "double-entry postings; per txn the amounts sum to zero", (
    Column("txn", pl.String, "transaction id", "lançamento", nullable=False),
    Column("date", pl.Date, "date", "data", "date", False),
    Column("account", pl.String, "account", "conta", nullable=False),
    Column("ticker", pl.String, "asset", "ativo"),
    Column("quantity", DEC, "units moved", "quantidade", "units"),
    _brl("amount_brl", "value", "valor"),
))  # fmt: skip
TAX_MONTH = Contract("tax_month", 1, "monthly IR on exchange-traded assets (DARF 6015)", (
    Column("month", pl.Date, "first day of the month", "mês", "date", False),
    _brl("stock_sales_brl", "stock swing sales", "vendas de ações"),
    Column("stock_exempt", pl.Boolean, "stock sales within the monthly exemption", "isenção de R$ 20 mil"),
    _brl("exempt_gain_brl", "exempt stock gain", "ganho isento"),
    _brl("result_common_brl", "swing result", "resultado comum"),
    _brl("result_day_brl", "day-trade result", "resultado day trade"),
    _brl("result_fii_brl", "FII/Fiagro result", "resultado FII"),
    _brl("loss_common_brl", "loss carried (<= 0)", "prejuízo a compensar comum"),
    _brl("loss_day_brl", "loss carried (<= 0)", "prejuízo a compensar day trade"),
    _brl("loss_fii_brl", "loss carried (<= 0)", "prejuízo a compensar FII"),
    _brl("tax_brl", "tax before IRRF", "imposto devido"),
    _brl("irrf_brl", "IRRF of the month", "IRRF do mês"),
    Column("irrf_estimated", pl.Boolean, "IRRF estimated where not reported", "IRRF estimado"),
    _brl("irrf_carry_brl", "IRRF to deduct later", "IRRF a compensar"),
    _brl("darf_brl", "DARF to pay", "DARF"),
    _brl("darf_carry_brl", "below R$ 10, carried", "DARF acumulado (< R$ 10)"),
    Column("darf_code", pl.String, "revenue code", "código"),
    Column("due", pl.Date, "due date", "vencimento", "date"),
    _brl("at_source_brl", "withheld at source outside the DARF", "retido na fonte"),
))  # fmt: skip


def _q(x: Decimal | None) -> Decimal | None:
    return None if x is None else x.quantize(Q)


def _frame(contract: Contract, rows: Sequence[Mapping[str, object]], sha: str, run: str) -> pl.DataFrame:
    schema = {c.name: c.dtype for c in contract.columns}
    df = pl.DataFrame([{k: r[k] for k in schema} for r in rows], schema=schema) if rows else pl.DataFrame(schema=schema)
    return contract.conform(df.with_columns(
        pl.lit(sha).alias("raw_sha256"),
        (pl.Series("raw_locator", [str(r.get("_loc", "")) for r in rows], dtype=pl.String) if rows
         else pl.lit("").alias("raw_locator")),
        pl.lit(run).alias("ingest_run_id"),
    ))  # fmt: skip


def run(zones: Zones, path: Path) -> tuple[LedgerResult, list[MonthTax], list[IncomeTax], str]:
    loaded = load(path)
    tickers = sorted({t.ticker for t in loaded.txns if t.ticker})
    classes = sources.classify(zones, tickers)
    start = min((t.date for t in loaded.txns), default=date(1986, 1, 1))
    stock, cash = sources.events(zones, tickers, start)
    res = build_ledger(loaded.txns, classes, stock, cash, rejected=loaded.rejected)
    cal = None
    try:
        from fin.ingest.anbima_calendar import load_calendar
        from fin.reference.calendar import Calendar

        cal = Calendar.from_frame(load_calendar(zones))
    except (FileNotFoundError, OSError, ValueError):
        cal = None
    return res, assess(res, calendar=cal), income_tax(res.income), loaded.sha256


def write(zones: Zones, path: Path) -> tuple[LedgerResult, list[MonthTax], list[IncomeTax]]:
    RawStore(zones.raw).put_file(path)
    res, months, inc, sha = run(zones, path)
    rid = f"ledger:{sha[:12]}"
    out = zones.core / "ledger"
    out.mkdir(parents=True, exist_ok=True)
    pos = [{"date": h.date, "ticker": h.ticker, "asset_class": h.asset_class, "quantity": _q(h.quantity),
            "cost_brl": _q(h.cost), "_loc": "ledger"} for h in res.history]  # fmt: skip
    real = [{"date": r.date, "ticker": r.ticker, "asset_class": r.asset_class, "mode": r.mode, "broker": r.broker,
             "quantity": _q(r.quantity), "sale_value_brl": _q(r.sale_value), "proceeds_brl": _q(r.proceeds),
             "cost_brl": _q(r.cost), "result_brl": _q(r.result), "irrf_brl": _q(r.irrf), "iof_brl": _q(r.iof),
             "ir_withheld_brl": _q(r.ir_withheld), "_loc": f"line {r.line}"} for r in res.realized]  # fmt: skip
    inc_rows = [{"date": i.date, "ticker": i.ticker, "kind": i.kind, "gross_brl": _q(i.gross), "irrf_brl": _q(i.irrf),
                 "status": i.status, "_loc": i.source} for i in res.income]  # fmt: skip
    post = [{"txn": p.txn, "date": p.date, "account": p.account, "ticker": p.ticker, "quantity": _q(p.quantity),
             "amount_brl": _q(p.amount), "_loc": p.txn} for p in res.postings]  # fmt: skip
    tm = [{"month": m.month, "stock_sales_brl": _q(m.stock_sales), "stock_exempt": m.stock_exempt,
           "exempt_gain_brl": _q(m.exempt_gain), "result_common_brl": _q(m.result["common"]),
           "result_day_brl": _q(m.result["day"]), "result_fii_brl": _q(m.result["fii"]),
           "loss_common_brl": _q(m.loss_carry["common"]), "loss_day_brl": _q(m.loss_carry["day"]),
           "loss_fii_brl": _q(m.loss_carry["fii"]), "tax_brl": _q(m.tax_total), "irrf_brl": _q(m.irrf_month),
           "irrf_estimated": m.irrf_estimated, "irrf_carry_brl": _q(m.irrf_carry), "darf_brl": _q(m.darf),
           "darf_carry_brl": _q(m.darf_carry), "darf_code": m.darf_code, "due": m.due,
           "at_source_brl": _q(m.at_source), "_loc": "ledger"} for m in months]  # fmt: skip
    for c, rows in ((POSITION, pos), (REALIZED, real), (INCOME, inc_rows), (POSTING, post), (TAX_MONTH, tm)):
        _frame(c, rows, sha, rid).write_parquet(out / f"{c.table}.parquet")
    return res, months, inc
