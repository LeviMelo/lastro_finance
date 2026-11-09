"""Monthly IR on exchange-traded assets for a resident individual, from the ledger's realized results (ADR-0033).

Categories and pools (IN RFB 1585/2015 arts. 56-65; Lei 8.668/1993 art. 18; rules in `rules.toml`):
- **common** (swing trade: stocks, units, BDRs, equity ETFs, other exchange assets): 15 %; stock gains of a month whose
  stock sales total at most R$ 20,000 are exempt (art. 59; not ETFs, BDRs or day trade, §2); a stock loss of such a
  month still enters the pool.
- **day** (day trade of the same): 20 %; its losses offset only day-trade gains (art. 64 sole §; art. 65 §10-11).
- **fii** (FII and Fiagro quotas, swing and day trade): 20 %; losses offset only FII gains (art. 37 §2).
- Losses carry forward without limit within their pool (art. 64).
- IRRF withheld (0.005 % on swing sales, 1 % on the positive day-trade result) is deducted from the month's tax and
  the rest carried forward (art. 63 §8, art. 65 §8); where the file reports no IRRF the engine estimates it.
- The DARF (code 6015) is due on the last business day of the following month (art. 56 §5) on the ANBIMA calendar;
  a total below R$ 10 is carried to the next month (Lei 9.430/1996 art. 68 §1).
- Fixed-income ETFs and Tesouro Direto are taxed at source (Lei 13.043/2014 art. 2; Lei 11.033/2004 art. 1): they are
  reported, not put in the DARF.

Rounding to the cent is half-up on each month's tax (not specified by the texts read; recorded in ADR-0033).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from fin.ledger.engine import Income, LedgerResult, Realized, month_end
from fin.ledger.transactions import ZERO
from fin.reference.calendar import Calendar, CalendarRangeError
from fin.tax.rules import TaxRules, default_rules

CENT = Decimal("0.01")
COMMON = ("stock", "unit", "bdr", "etf", "other")
FII = ("fii", "fiagro")
AT_SOURCE = ("etf_fixed_income", "tesouro")


def cents(x: Decimal) -> Decimal:
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


def pool(r: Realized) -> str | None:
    if r.asset_class in FII:
        return "fii"
    if r.asset_class in AT_SOURCE:
        return None
    return "day" if r.mode == "day" else "common"


@dataclass(frozen=True)
class MonthTax:
    month: date  # first day of the month
    stock_sales: Decimal  # BRL, stock swing sales (the exemption test)
    stock_exempt: bool
    exempt_gain: Decimal  # BRL, exempt stock net gain
    result: dict[str, Decimal]  # pool -> net result of the month
    loss_carry: dict[str, Decimal]  # pool -> loss carried forward after the month (<= 0)
    tax: dict[str, Decimal]  # pool -> tax before IRRF
    irrf_month: Decimal  # withheld in the month (reported or estimated)
    irrf_estimated: bool
    irrf_used: Decimal
    irrf_carry: Decimal
    darf: Decimal  # BRL to pay with code 6015 (0 when below the minimum, carried)
    darf_carry: Decimal  # below-minimum amount carried to the next month
    darf_code: str
    due: date
    at_source: Decimal  # BRL withheld at source on fixed-income ETFs and Tesouro (outside the DARF)

    @property
    def tax_total(self) -> Decimal:
        return sum(self.tax.values(), ZERO)


def due_date(month: date, calendar: Calendar | None) -> date:
    last = month_end(month_end(month) + timedelta(days=1))
    if calendar is None:
        return last
    try:
        return calendar.preceding(last)
    except CalendarRangeError:
        return last


def _irrf(rows: list[Realized], rules: TaxRules, month: date) -> tuple[Decimal, bool]:
    """IRRF of the month: as reported, else estimated (0.005 % of swing sales per broker with the R$ 1 dispense;
    1 % of the positive day-trade result per day and broker)."""
    total, estimated = ZERO, False
    swing: dict[str, Decimal] = defaultdict(lambda: ZERO)
    day: dict[tuple[date, str], Decimal] = defaultdict(lambda: ZERO)
    for r in rows:
        if r.asset_class in AT_SOURCE:
            continue
        if r.irrf is not None:
            total += r.irrf
        elif r.mode == "day":
            day[(r.date, r.broker)] += r.result
            estimated = True
        else:
            swing[r.broker] += r.sale_value * rules.dec("irrf_swing_rate", month)
            estimated = True
    dispense = rules.dec("irrf_swing_dispense", month)
    total += sum((cents(v) for v in swing.values() if cents(v) > dispense), ZERO)
    total += sum((cents(v * rules.dec("irrf_day_trade_rate", month)) for v in day.values() if v > 0), ZERO)
    return total, estimated


def assess(result: LedgerResult, rules: TaxRules | None = None, calendar: Calendar | None = None) -> list[MonthTax]:
    """One row per month from the first realized sale to the last, carrying losses, IRRF and small DARFs."""
    rules = rules or default_rules()
    by_month: dict[date, list[Realized]] = defaultdict(list)
    for r in result.realized:
        by_month[r.date.replace(day=1)].append(r)
    if not by_month:
        return []
    months, m = [], min(by_month)
    while m <= max(by_month):
        months.append(m)
        m = month_end(m) + timedelta(days=1)
    carry = {"common": ZERO, "day": ZERO, "fii": ZERO}
    irrf_carry = darf_carry = ZERO
    out = []
    for m in months:
        rows = by_month.get(m, [])
        stock = [r for r in rows if r.asset_class == "stock" and r.mode == "swing"]
        stock_sales = sum((r.sale_value for r in stock), ZERO)
        exempt = stock_sales <= rules.dec("stock_exemption_limit", m)
        stock_result = sum((r.result for r in stock), ZERO)
        exempt_gain = stock_result if exempt and stock_result > 0 else ZERO
        res = {"common": -exempt_gain, "day": ZERO, "fii": ZERO}
        for r in rows:
            p = pool(r)
            if p is not None:
                res[p] += r.result
        rate = {"common": rules.dec("swing_rate", m), "day": rules.dec("day_trade_rate", m),
                "fii": rules.dec("fii_rate", m)}  # fmt: skip
        tax = {}
        for p in res:
            base = res[p] + carry[p]
            if base > 0:
                tax[p] = cents(base * rate[p])
                carry[p] = ZERO
            else:
                tax[p] = ZERO
                carry[p] = base
        irrf_m, est = _irrf(rows, rules, m)
        avail = irrf_m + irrf_carry
        total = sum(tax.values(), ZERO)
        used = min(avail, total)
        irrf_carry = avail - used
        due_amt = total - used + darf_carry
        if due_amt < rules.dec("darf_minimum", m):
            darf, darf_carry = ZERO, due_amt
        else:
            darf, darf_carry = due_amt, ZERO
        at_source = sum((r.iof + r.ir_withheld + (r.irrf or ZERO) for r in rows if r.asset_class in AT_SOURCE), ZERO)
        out.append(MonthTax(m, stock_sales, exempt, exempt_gain, res, dict(carry), tax, irrf_m, est, used, irrf_carry,
                            darf, darf_carry, rules.text("darf_code_individual", m), due_date(m, calendar),
                            at_source))  # fmt: skip
    return out


@dataclass(frozen=True)
class IncomeTax:
    month: date
    payer: str  # issuer id, else ticker
    kind: str
    gross: Decimal  # BRL
    subject: Decimal  # BRL subject to the withholding (dividends: excludes grandfathered amounts)
    irrf_expected: Decimal
    irrf_recorded: Decimal
    rule: str


def income_tax(income: list[Income], rules: TaxRules | None = None) -> list[IncomeTax]:
    """Withholding on JCP (Lei 9.249/1995 art. 9 §2) and, from 2026, on a payer's dividends above R$ 50,000 in a month
    (Lei 9.250/1995 art. 6-A); FII/Fiagro distributions are exempt under Lei 11.033/2004 art. 3 III (the fund's
    100-holder and the holder's 10 % conditions are not checked here)."""
    rules = rules or default_rules()
    groups: dict[tuple[date, str, str], list[Income]] = defaultdict(list)
    for i in income:
        groups[(i.date.replace(day=1), i.payer or i.ticker, i.kind)].append(i)
    out = []
    for (m, payer, kind), rows in sorted(groups.items()):
        gross = sum((i.gross for i in rows), ZERO)
        rec = sum((i.irrf for i in rows), ZERO)
        if kind == "JCP":
            exp = sum((cents(i.gross * rules.dec("jcp_rate", i.approved_on or i.date)) for i in rows), ZERO)
            out.append(IncomeTax(m, payer, kind, gross, gross, exp, rec, rules.rule("jcp_rate", m).ref))
        elif kind == "DIVIDEND" and rules.has("dividend_monthly_rate", m):
            cut = date.fromisoformat(rules.text("dividend_grandfather_approved_by", m))
            subject = sum((i.gross for i in rows if not (i.approved_on and i.approved_on <= cut)), ZERO)
            over = subject > rules.dec("dividend_monthly_threshold", m)
            exp = cents(subject * rules.dec("dividend_monthly_rate", m)) if over else ZERO
            out.append(IncomeTax(m, payer, kind, gross, subject, exp, rec, rules.rule("dividend_monthly_rate", m).ref))
        else:
            out.append(IncomeTax(m, payer, kind, gross, ZERO, ZERO, rec, "isento" if kind != "COUPON" else "na fonte"))
    return out
