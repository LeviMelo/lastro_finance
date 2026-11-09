"""The ledger (PLAN §5, ADR-0033): transactions and corporate events -> postings, positions and realized results.

- **Average cost** (preço médio): one weighted-average cost per asset for the taxpayer (IN RFB 1585/2015 art. 58),
  across brokers; quantities are also kept per broker for reconciliation with custody statements.
- **Day trade** (art. 65): per day, broker and asset, the first buy is paired with the first sell, successively
  (§3); stock held before the day is not used (§2). The unpaired rest is a swing trade at average cost.
- **Corporate events** (core `corporate_event`, applied statuses only): splits and reverse splits change the
  quantity and keep the total cost (art. 58 §7 II); bonuses add shares at the cost the company attributed (§1), which
  only the owner's file carries (a BONUS row): without it the shares enter at zero cost and an issue says so; cash
  events of a held asset become expected income rows unless the file reports them; amortization and capital returns
  reduce the cost (§8).
- **Tesouro Direto**: lots by purchase date, sold first-in first-out, with the regressive IR and the IOF of the first
  30 days withheld at source (Lei 11.033/2004 art. 1; Decreto 6.306/2007 art. 32).
- **Double entry**: every movement is a transaction whose postings sum to zero in BRL.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal

from fin.ledger.transactions import TRADES, ZERO, Txn
from fin.tax.rules import TaxRules, default_rules

EXCHANGE = ("stock", "unit", "bdr", "etf", "etf_fixed_income", "fii", "fiagro", "other")  # day trade applies
CENT = Decimal("0.01")
MATCH_DAYS = 10  # a file row this close to a corporate event of the same asset and kind is that event


class LedgerError(ValueError):
    """The transactions cannot describe a real portfolio (e.g. selling more than held): fix the file."""


@dataclass(frozen=True)
class StockEvent:
    event_id: str
    ticker: str
    event_type: str  # SPLIT, REVERSE_SPLIT, BONUS
    ex_date: date
    ratio_num: int  # holdings after = holdings before * num / den
    ratio_den: int


@dataclass(frozen=True)
class CashEvent:
    event_id: str
    ticker: str
    event_type: str  # DIVIDEND, JCP, INCOME, AMORTIZATION
    data_com: date
    payment_date: date | None
    approved_on: date | None
    cash_per_share: Decimal
    payer: str = ""  # the paying company (issuer id) for the monthly dividend rule


@dataclass
class _Open:
    txn: Txn
    rem: Decimal


@dataclass
class Lot:
    opened: date
    qty: Decimal
    cost: Decimal  # BRL, total


@dataclass
class Holding:
    asset_class: str
    qty: Decimal = ZERO
    cost: Decimal = ZERO  # BRL, total (average cost = cost / qty)
    by_broker: dict[str, Decimal] = field(default_factory=lambda: defaultdict(lambda: ZERO))
    lots: list[Lot] = field(default_factory=list)  # Tesouro only

    @property
    def avg(self) -> Decimal:
        return self.cost / self.qty if self.qty else ZERO


@dataclass(frozen=True)
class PositionRow:
    date: date
    ticker: str
    asset_class: str
    quantity: Decimal
    cost: Decimal  # BRL, total
    by_broker: dict[str, Decimal]


@dataclass(frozen=True)
class Realized:
    date: date
    ticker: str
    asset_class: str
    mode: str  # swing, day, fixed_income
    broker: str
    quantity: Decimal
    sale_value: Decimal  # BRL, quantity * price (the 'valor das alienações' of the exemption)
    proceeds: Decimal  # BRL, net of the row's fees
    cost: Decimal  # BRL
    irrf: Decimal | None  # BRL reported on the row (prorated), None if not reported
    iof: Decimal = ZERO  # Tesouro: IOF withheld
    ir_withheld: Decimal = ZERO  # Tesouro: IR withheld at source
    line: int = 0

    @property
    def result(self) -> Decimal:
        return self.proceeds - self.cost


@dataclass(frozen=True)
class Income:
    date: date
    ticker: str
    asset_class: str
    kind: str
    gross: Decimal
    irrf: Decimal
    status: str  # reported (file) or expected (from corporate_event)
    approved_on: date | None
    payer: str
    source: str


@dataclass(frozen=True)
class Posting:
    txn: str
    date: date
    account: str
    ticker: str
    quantity: Decimal
    amount: Decimal  # BRL; per transaction the amounts sum to zero


@dataclass
class LedgerResult:
    holdings: dict[str, Holding]
    history: list[PositionRow]  # position after each day it changed
    realized: list[Realized]
    income: list[Income]
    postings: list[Posting]
    issues: list[str]
    rejected: list[tuple[int, str, str]]

    def positions_on(self, d: date) -> dict[str, tuple[Decimal, Decimal]]:
        """ticker -> (quantity, total cost) at the end of `d`."""
        out: dict[str, tuple[Decimal, Decimal]] = {}
        for h in self.history:
            if h.date <= d:
                out[h.ticker] = (h.quantity, h.cost)
        return {k: v for k, v in out.items() if v[0] != 0}


def _jcp_irrf(rules: TaxRules, ev_date: date, gross: Decimal) -> Decimal:
    return (gross * rules.dec("jcp_rate", ev_date)).quantize(CENT, rounding=ROUND_HALF_UP)


class Ledger:
    def __init__(self, classes: dict[str, str], rules: TaxRules | None = None) -> None:
        self.classes = classes
        self.rules = rules or default_rules()
        self.h: dict[str, Holding] = {}
        self.realized: list[Realized] = []
        self.income: list[Income] = []
        self.postings: list[Posting] = []
        self.issues: list[str] = []
        self.history: list[PositionRow] = []
        self._n = 0

    # -- bookkeeping ------------------------------------------------------------------------------------------------
    def _txn(self, d: date, legs: list[tuple[str, str, Decimal, Decimal]]) -> None:
        self._n += 1
        tid = f"T{self._n:06d}"
        total = sum((a for _, _, _, a in legs), ZERO)
        if total != 0:
            raise AssertionError(f"postings of {tid} sum to {total}")
        self.postings += [Posting(tid, d, acc, tk, q, a) for acc, tk, q, a in legs]

    def _hold(self, ticker: str, cls: str = "") -> Holding:
        if ticker not in self.h:
            self.h[ticker] = Holding(cls or self.classes.get(ticker, "other"))
        return self.h[ticker]

    def _class(self, t: Txn) -> str:
        if t.asset_class:
            return t.asset_class
        if t.ticker.startswith("Tesouro "):
            return "tesouro"
        return self.classes.get(t.ticker, "other")

    # -- movements ------------------------------------------------------------------------------------------------
    def buy(self, d: date, broker: str, ticker: str, cls: str, qty: Decimal, cost: Decimal) -> None:
        h = self._hold(ticker, cls)
        h.qty += qty
        h.cost += cost
        h.by_broker[broker] += qty
        if cls == "tesouro":
            h.lots.append(Lot(d, qty, cost))
        self._txn(d, [(f"custody:{broker}", ticker, qty, cost), (f"cash:{broker}", "", ZERO, -cost)])

    def sell_swing(self, t: Txn, qty: Decimal, fees: Decimal, irrf: Decimal | None) -> None:
        cls = self._class(t)
        h = self._hold(t.ticker, cls)
        if qty > h.qty or qty > h.by_broker[t.broker]:
            raise LedgerError(
                f"linha {t.line}: venda de {qty} {t.ticker} em {t.date} na corretora '{t.broker}', "
                f"posição {h.by_broker[t.broker]}"
            )
        sale = qty * t.price
        proceeds = sale - fees
        if cls == "tesouro":
            self._sell_tesouro(t, h, qty, sale, proceeds)
            return
        cost = h.avg * qty
        h.qty -= qty
        h.cost -= cost
        h.by_broker[t.broker] -= qty
        if h.qty == 0:
            h.cost = ZERO
        self.realized.append(Realized(t.date, t.ticker, cls, "swing", t.broker, qty, sale, proceeds, cost, irrf,
                                      line=t.line))  # fmt: skip
        self._sale_postings(t, cls, "swing", qty, proceeds, cost, irrf)

    def _sale_postings(self, t: Txn, cls: str, mode: str, qty: Decimal, proceeds: Decimal, cost: Decimal,
                       irrf: Decimal | None) -> None:  # fmt: skip
        legs = [
            (f"custody:{t.broker}", t.ticker, -qty, -cost),
            (f"cash:{t.broker}", "", ZERO, proceeds - (irrf or ZERO)),
            (f"result:{cls}:{mode}", t.ticker, ZERO, cost - proceeds),
        ]
        if irrf:
            legs.append(("tax:irrf_credit", "", ZERO, irrf))
        self._txn(t.date, legs)

    def _sell_tesouro(self, t: Txn, h: Holding, qty: Decimal, sale: Decimal, proceeds: Decimal) -> None:
        left = qty
        while left > 0:
            lot = h.lots[0]
            q = min(left, lot.qty)
            cost = lot.cost * q / lot.qty
            part = proceeds * q / qty
            days = (t.date - lot.opened).days
            gain = part - cost
            iof = (max(gain, ZERO) * self.rules.bracket("iof_regressive", t.date, days)).quantize(
                CENT, rounding=ROUND_HALF_UP
            )
            ir = (max(gain - iof, ZERO) * self.rules.bracket("fixed_income_rate", t.date, days)).quantize(
                CENT, rounding=ROUND_HALF_UP
            )
            self.realized.append(Realized(t.date, t.ticker, "tesouro", "fixed_income", t.broker, q, sale * q / qty,
                                          part, cost, None, iof, ir, t.line))  # fmt: skip
            tax = iof + ir
            self._txn(t.date, [
                (f"custody:{t.broker}", t.ticker, -q, -cost),
                (f"cash:{t.broker}", "", ZERO, part - tax),
                ("tax:withheld_fixed_income", "", ZERO, tax),
                ("result:tesouro:fixed_income", t.ticker, ZERO, cost - part),
            ])  # fmt: skip
            lot.qty -= q
            lot.cost -= cost
            if lot.qty == 0:
                h.lots.pop(0)
            left -= q
        h.qty -= qty
        h.cost = sum((lot.cost for lot in h.lots), ZERO)
        h.by_broker[t.broker] -= qty

    def trades_of_day(self, trades: list[Txn]) -> None:
        """One day's trades of one broker and asset: day-trade pairing, then the rest at average cost."""
        cls = self._class(trades[0])
        if cls not in EXCHANGE:
            for t in trades:
                if t.kind == "BUY":
                    self.buy(t.date, t.broker, t.ticker, cls, t.quantity, t.value + t.fees)
                else:
                    self.sell_swing(t, t.quantity, t.fees, t.irrf)
            return
        buys: deque[_Open] = deque()
        sells: deque[_Open] = deque()
        for t in trades:
            own, other = (buys, sells) if t.kind == "BUY" else (sells, buys)
            left = t.quantity
            while left > 0 and other:
                o = other[0]
                m = min(left, o.rem)
                b, s = (t, o.txn) if t.kind == "BUY" else (o.txn, t)
                self._day_trade(b, s, m)
                left -= m
                o.rem -= m
                if o.rem == 0:
                    other.popleft()
            if left > 0:
                own.append(_Open(t, left))
        for o in buys:
            t = o.txn
            self.buy(t.date, t.broker, t.ticker, cls, o.rem, o.rem * t.price + t.fees * o.rem / t.quantity)
        for o in sells:
            t = o.txn
            irrf = None if t.irrf is None else t.irrf * o.rem / t.quantity
            self.sell_swing(t, o.rem, t.fees * o.rem / t.quantity, irrf)

    def _day_trade(self, b: Txn, s: Txn, m: Decimal) -> None:
        cls = self._class(b)
        cost = m * b.price + b.fees * m / b.quantity
        sale = m * s.price
        proceeds = sale - s.fees * m / s.quantity
        irrf = None if s.irrf is None else s.irrf * m / s.quantity
        self.realized.append(Realized(s.date, s.ticker, cls, "day", s.broker, m, sale, proceeds, cost, irrf,
                                      line=s.line))  # fmt: skip
        self._txn(s.date, [
            (f"cash:{b.broker}", "", ZERO, -cost),
            (f"cash:{s.broker}", "", ZERO, proceeds - (irrf or ZERO)),
            (f"result:{cls}:day", s.ticker, ZERO, cost - proceeds),
        ] + ([("tax:irrf_credit", "", ZERO, irrf)] if irrf else []))  # fmt: skip

    def stock_event(self, e: StockEvent, bonus_row: Txn | None) -> None:
        h = self.h.get(e.ticker)
        if h is None or h.qty == 0:
            return
        if e.event_type == "BONUS" and bonus_row is not None:
            return  # the file's BONUS row carries quantity and attributed cost; applied as a movement
        legs: list[tuple[str, str, Decimal, Decimal]] = []
        for broker, q in list(h.by_broker.items()):
            if q == 0:
                continue
            exact = q * e.ratio_num / e.ratio_den
            new = exact.to_integral_value(rounding=ROUND_FLOOR)
            if new != exact:
                self.issues.append(
                    f"{e.ex_date} {e.ticker}: {e.event_type} {e.ratio_num}:{e.ratio_den} deixa fração "
                    f"{exact - new} na corretora '{broker}' (leilão de frações: informe a venda)"
                )
            h.by_broker[broker] = new
            legs.append((f"custody:{broker}", e.ticker, new - q, ZERO))
        new_total = sum(h.by_broker.values(), ZERO)
        if e.event_type == "BONUS":
            self.issues.append(
                f"{e.ex_date} {e.ticker}: bonificação {e.ratio_num}:{e.ratio_den} aplicada a custo zero; o custo "
                "atribuído pela companhia (IN RFB 1585/2015 art. 58 §1) deve vir numa linha BONUS do arquivo"
            )
        h.qty = new_total
        if legs:
            self._txn(e.ex_date, legs)

    def bonus(self, t: Txn) -> None:
        cost = t.quantity * t.price
        h = self._hold(t.ticker, self._class(t))
        h.qty += t.quantity
        h.cost += cost
        h.by_broker[t.broker] += t.quantity
        self._txn(t.date, [(f"custody:{t.broker}", t.ticker, t.quantity, cost), ("equity:bonus", t.ticker, ZERO,
                                                                                    -cost)])  # fmt: skip

    def transfer_in(self, t: Txn) -> None:
        cost = t.quantity * t.price
        cls = self._class(t)
        h = self._hold(t.ticker, cls)
        h.qty += t.quantity
        h.cost += cost
        h.by_broker[t.broker] += t.quantity
        if cls == "tesouro":
            h.lots.append(Lot(t.date, t.quantity, cost))
        self._txn(t.date, [(f"custody:{t.broker}", t.ticker, t.quantity, cost), ("equity:opening", t.ticker, ZERO,
                                                                                    -cost)])  # fmt: skip

    def cash(self, d: date, ticker: str, kind: str, gross: Decimal, irrf: Decimal, status: str, broker: str,
             approved_on: date | None, payer: str, source: str) -> None:  # fmt: skip
        cls = self.classes.get(ticker, "other") if ticker else ""
        if kind == "FEE":
            self._txn(d, [(f"cash:{broker}", "", ZERO, -gross), ("expense:fees", "", ZERO, gross)])
            return
        legs = [(f"cash:{broker}", "", ZERO, gross - irrf)]
        if irrf:
            legs.append(("tax:withheld_income", "", ZERO, irrf))
        if kind == "AMORTIZATION":  # capital returned: reduces cost (IN RFB 1585/2015 art. 58 §8)
            h = self.h.get(ticker)
            cut = min(gross, h.cost) if h else ZERO
            if h:
                h.cost -= cut
            legs.append((f"custody:{broker}", ticker, ZERO, -cut))
            if gross - cut:
                legs.append((f"result:{cls}:amortization", ticker, ZERO, cut - gross))
        else:
            legs.append((f"income:{kind.lower()}", ticker, ZERO, -gross))
        self._txn(d, legs)
        self.income.append(Income(d, ticker, cls, kind, gross, irrf, status, approved_on, payer, source))

    def snapshot(self, d: date, tickers: set[str]) -> None:
        for tk in sorted(tickers):
            h = self.h.get(tk)
            if h is not None:
                self.history.append(PositionRow(d, tk, h.asset_class, h.qty, h.cost, dict(h.by_broker)))


def build_ledger(
    txns: list[Txn],
    classes: dict[str, str] | None = None,
    stock_events: list[StockEvent] | None = None,
    cash_events: list[CashEvent] | None = None,
    rules: TaxRules | None = None,
    rejected: list[tuple[int, str, str]] | None = None,
) -> LedgerResult:
    """Run the ledger over the transactions (any order; sorted by date, then file line)."""
    led = Ledger(classes or {}, rules)
    txns = sorted(txns, key=lambda t: (t.date, t.line))
    stock_events = sorted(stock_events or [], key=lambda e: e.ex_date)
    cash_events = list(cash_events or [])
    by_day: dict[date, list[Txn]] = defaultdict(list)
    for t in txns:
        by_day[t.date].append(t)
    reported = [(t.ticker, t.kind, t.date) for t in txns if t.kind in ("DIVIDEND", "JCP", "INCOME", "AMORTIZATION")]
    bonus_rows = [t for t in txns if t.kind == "BONUS"]
    entitled: dict[date, list[tuple[CashEvent, Decimal, str]]] = defaultdict(
        list
    )  # payment day -> (event, qty, broker)
    days = sorted(
        set(by_day)
        | {e.ex_date for e in stock_events}
        | {e.data_com for e in cash_events}
        | {e.payment_date for e in cash_events if e.payment_date}
    )
    for d in days:
        touched: set[str] = set()
        for e in (e for e in stock_events if e.ex_date == d):
            br = next((b for b in bonus_rows if b.ticker == e.ticker and abs((b.date - d).days) <= MATCH_DAYS), None)
            led.stock_event(e, br if e.event_type == "BONUS" else None)
            touched.add(e.ticker)
        groups: dict[tuple[str, str], list[Txn]] = defaultdict(list)
        for t in by_day.get(d, []):
            if t.kind in TRADES:
                groups[(t.broker, t.ticker)].append(t)
        for (_, tk), ts in groups.items():
            led.trades_of_day(ts)
            touched.add(tk)
        for t in by_day.get(d, []):
            if t.kind == "BONUS":
                led.bonus(t)
            elif t.kind == "TRANSFER_IN":
                led.transfer_in(t)
            elif t.kind in ("DIVIDEND", "JCP", "INCOME", "AMORTIZATION", "COUPON", "FEE"):
                irrf = t.irrf
                if irrf is None:
                    irrf = _jcp_irrf(led.rules, t.approved_on or t.date, t.amount) if t.kind == "JCP" else ZERO
                led.cash(t.date, t.ticker, t.kind, t.amount, irrf, "reported", t.broker, t.approved_on, "", "file")
            else:
                continue
            touched.add(t.ticker)
        for e in (e for e in cash_events if e.data_com == d):  # entitled: holders at the end of data com
            h = led.h.get(e.ticker)
            if h is None:
                continue
            if any(tk == e.ticker and k == e.event_type and abs((dd - (e.payment_date or d)).days) <= MATCH_DAYS
                   for tk, k, dd in reported):  # fmt: skip
                continue
            for broker, q in h.by_broker.items():
                if q > 0:
                    entitled[e.payment_date or d].append((e, q, broker))
        for e, q, broker in entitled.pop(d, []):
            _pay(led, d, e, q, broker)
        led.snapshot(d, touched - {""})
    for pd in sorted(entitled):  # payments after the last transaction date
        for e, q, broker in entitled[pd]:
            _pay(led, pd, e, q, broker)
    return LedgerResult(led.h, led.history, led.realized, led.income, led.postings, led.issues, rejected or [])


def _pay(led: Ledger, d: date, e: CashEvent, q: Decimal, broker: str) -> None:
    gross = (q * e.cash_per_share).quantize(CENT, rounding=ROUND_HALF_UP)
    irrf = _jcp_irrf(led.rules, e.approved_on or e.data_com, gross) if e.event_type == "JCP" else ZERO
    led.cash(d, e.ticker, e.event_type, gross, irrf, "expected", broker, e.approved_on, e.payer,
             f"corporate_event:{e.event_id}")  # fmt: skip


def month_end(d: date) -> date:
    nxt = (d.replace(day=1) + timedelta(days=32)).replace(day=1)
    return nxt - timedelta(days=1)
