"""The transactions file (Stage I, ADR-0033): the owner's trades and cash events as a CSV, one row per movement.

Columns (header required; empty cells allowed where noted):

    date,kind,ticker,quantity,price,amount,fees,irrf,broker,asset_class,approved_on,note

- `kind`: BUY, SELL (quantity, price, fees), BONUS (quantity received, price = cost per share the company attributed,
  IN RFB 1585/2015 art. 58 §1), TRANSFER_IN (quantity, price = average cost brought in), DIVIDEND, JCP, INCOME
  (FII/Fiagro distribution), AMORTIZATION, COUPON (amount = gross BRL, irrf = withheld), FEE (amount).
- `fees`: brokerage, emoluments and settlement fees of the row in BRL (IN RFB 1585/2015 art. 56 §3).
- `irrf`: tax withheld on the row as the broker reported it; empty = not reported (the engine estimates it).
- `asset_class`: optional override (stock, unit, bdr, etf, etf_fixed_income, fii, fiagro, tesouro, other).
- Numbers use `.` as the decimal separator; money is BRL. Rows keep file order within a day (day-trade matching
  pairs the first buy with the first sell, IN RFB 1585/2015 art. 65 §3).

A row that does not parse is returned in `rejected` with the reason, never dropped (invariant 11).
"""

from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

KINDS = ("BUY", "SELL", "BONUS", "TRANSFER_IN", "DIVIDEND", "JCP", "INCOME", "AMORTIZATION", "COUPON", "FEE")
TRADES = ("BUY", "SELL")
CASH = ("DIVIDEND", "JCP", "INCOME", "AMORTIZATION", "COUPON", "FEE")
CLASSES = ("stock", "unit", "bdr", "etf", "etf_fixed_income", "fii", "fiagro", "tesouro", "other")
COLUMNS = ("date", "kind", "ticker", "quantity", "price", "amount", "fees", "irrf", "broker", "asset_class",
           "approved_on", "note")  # fmt: skip
ZERO = Decimal(0)


@dataclass(frozen=True)
class Txn:
    line: int  # 1-based line in the file (the header is line 1): the row's locator
    date: date
    kind: str
    ticker: str
    quantity: Decimal = ZERO
    price: Decimal = ZERO  # BRL per unit
    amount: Decimal = ZERO  # BRL, gross, for cash rows
    fees: Decimal = ZERO  # BRL
    irrf: Decimal | None = None  # BRL withheld as reported; None = not reported
    broker: str = ""
    asset_class: str = ""
    approved_on: date | None = None  # dividends/JCP: the approval date (Lei 15.270/2025 art. 6-A §3)
    note: str = ""
    source: str = "file"  # "file" or "corporate_event:<event_id>" for rows the ledger generates

    @property
    def value(self) -> Decimal:
        return self.quantity * self.price


@dataclass(frozen=True)
class Loaded:
    txns: list[Txn]
    rejected: list[tuple[int, str, str]]  # (line, raw text, reason)
    sha256: str


def _dec(s: str, name: str, *, required: bool = False) -> Decimal:
    s = s.strip()
    if not s:
        if required:
            raise ValueError(f"{name} vazio")
        return ZERO
    if "," in s:
        raise ValueError(f"{name} '{s}': use '.' como separador decimal")
    try:
        return Decimal(s)
    except InvalidOperation as e:
        raise ValueError(f"{name} '{s}' não é número") from e


def parse_row(line: int, r: dict[str, str]) -> Txn:
    kind = r.get("kind", "").strip().upper()
    if kind not in KINDS:
        raise ValueError(f"kind '{kind}' desconhecido")
    ticker = r.get("ticker", "").strip()
    if not ticker and kind != "FEE":
        raise ValueError("ticker vazio")
    cls = r.get("asset_class", "").strip().lower()
    if cls and cls not in CLASSES:
        raise ValueError(f"asset_class '{cls}' desconhecida")
    irrf_s = r.get("irrf", "").strip()
    ap = r.get("approved_on", "").strip()
    t = Txn(
        line=line,
        date=date.fromisoformat(r.get("date", "").strip()),
        kind=kind,
        ticker=ticker.upper() if not ticker.startswith("Tesouro") else ticker,
        quantity=_dec(r.get("quantity", ""), "quantity", required=kind in (*TRADES, "BONUS", "TRANSFER_IN")),
        price=_dec(r.get("price", ""), "price", required=kind in TRADES),
        amount=_dec(r.get("amount", ""), "amount", required=kind in CASH),
        fees=_dec(r.get("fees", ""), "fees"),
        irrf=_dec(irrf_s, "irrf") if irrf_s else None,
        broker=r.get("broker", "").strip(),
        asset_class=cls,
        approved_on=date.fromisoformat(ap) if ap else None,
        note=r.get("note", "").strip(),
    )
    if t.quantity < 0 or t.price < 0 or t.fees < 0 or t.amount < 0:
        raise ValueError("valores negativos não são aceitos (o sentido vem de kind)")
    return t


def load(path: Path) -> Loaded:
    data = path.read_bytes()
    text = data.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    missing = [c for c in ("date", "kind", "ticker") if c not in (reader.fieldnames or [])]
    if missing:
        raise ValueError(f"{path}: cabeçalho sem as colunas {missing}")
    lines = text.splitlines()
    txns, rejected = [], []
    for r in reader:
        line = reader.line_num
        try:
            txns.append(parse_row(line, r))
        except (ValueError, TypeError) as e:
            rejected.append((line, lines[line - 1] if line - 1 < len(lines) else "", str(e)))
    return Loaded(txns, rejected, hashlib.sha256(data).hexdigest())
