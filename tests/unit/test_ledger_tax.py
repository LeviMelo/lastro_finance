"""Stage I worked examples (ADR-0033): ledger average cost, day trade, corporate events, and the monthly IR."""

from __future__ import annotations

from datetime import date
from decimal import Decimal as D
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from fin.ledger.engine import CashEvent, LedgerError, LedgerResult, StockEvent, build_ledger
from fin.ledger.transactions import Txn, load
from fin.reference.calendar import Calendar
from fin.tax.engine import assess, income_tax
from fin.tax.rules import TaxRules, default_rules

S = {"WXYZ3": "stock", "ABCD3": "stock", "BOVA11": "etf", "HGLG11": "fii", "AAPL34": "bdr"}


def T(line: int, d: str, kind: str, tk: str, q: str = "0", p: str = "0", fees: str = "0", irrf: str | None = None,
      broker: str = "X", amount: str = "0", approved: str | None = None) -> Txn:  # fmt: skip
    ap = date.fromisoformat(approved) if approved else None
    return Txn(line, date.fromisoformat(d), kind, tk, D(q), D(p), D(amount), D(fees),
               None if irrf is None else D(irrf), broker, approved_on=ap)  # fmt: skip


def postings_balance(res: LedgerResult) -> None:
    tot: dict[str, D] = {}
    for p in res.postings:
        tot[p.txn] = tot.get(p.txn, D(0)) + p.amount
    assert all(v == 0 for v in tot.values())


def test_receita_worked_example() -> None:
    """Receita Federal 'Cálculo e Pagamento do Imposto' (bolsa): buy 1,000 WXYZ3 at 50 with R$ 15 fees, sell at 60
    with R$ 18 fees and R$ 3 IRRF: gain 9,967.00, tax 1,495.05, to pay 1,492.05 with code 6015 by the end of March."""
    txns = [T(2, "2024-01-10", "BUY", "WXYZ3", "1000", "50", "15"),
            T(3, "2024-02-26", "SELL", "WXYZ3", "1000", "60", "18", irrf="3")]  # fmt: skip
    res = build_ledger(txns, S)
    [r] = res.realized
    assert r.result == D("9967.00")
    feb = next(m for m in assess(res) if m.month == date(2024, 2, 1))
    assert feb.tax_total == D("1495.05") and feb.darf == D("1492.05") and feb.darf_code == "6015"
    assert not feb.stock_exempt
    postings_balance(res)


def test_exemption_threshold_edge() -> None:
    at = [T(2, "2024-01-02", "BUY", "WXYZ3", "1000", "10"), T(3, "2024-03-05", "SELL", "WXYZ3", "1000", "20")]
    over = [T(2, "2024-01-02", "BUY", "WXYZ3", "1000", "10"), T(3, "2024-03-05", "SELL", "WXYZ3", "1000", "20.01")]
    m_at = assess(build_ledger(at, S))[-1]
    m_over = assess(build_ledger(over, S))[-1]
    assert m_at.stock_sales == D("20000") and m_at.stock_exempt and m_at.darf == 0 and m_at.exempt_gain == D("10000")
    assert not m_over.stock_exempt and m_over.tax_total == D("1501.50")  # 15 % of 10,010


def test_exemption_not_for_etf_and_stock_loss_carries() -> None:
    txns = [
        T(2, "2024-01-02", "BUY", "BOVA11", "100", "100"),
        T(3, "2024-01-03", "BUY", "WXYZ3", "100", "50"),
        T(4, "2024-02-05", "SELL", "BOVA11", "100", "110"),  # ETF gain 1,000 in a small month: taxed
        T(5, "2024-02-06", "SELL", "WXYZ3", "100", "40"),
    ]  # stock loss 1,000 in an exempt month: offsets
    feb = assess(build_ledger(txns, S))[0]
    assert feb.stock_exempt and feb.result["common"] == 0 and feb.tax_total == 0


def test_day_trade_pairing_and_separate_pool() -> None:
    txns = [T(2, "2024-01-02", "BUY", "WXYZ3", "100", "10"),  # swing stock held before the day
            T(3, "2024-04-10", "SELL", "WXYZ3", "100", "12"),  # first sell paired with the first buy below
            T(4, "2024-04-10", "BUY", "WXYZ3", "100", "11"),
            T(5, "2024-04-11", "BUY", "ABCD3", "10", "100"),
            T(6, "2024-04-11", "SELL", "ABCD3", "10", "90")]  # fmt: skip
    res = build_ledger(txns, S)
    day = [r for r in res.realized if r.mode == "day"]
    assert [(r.ticker, r.result) for r in day] == [("WXYZ3", D("100")), ("ABCD3", D("-100"))]
    assert res.holdings["WXYZ3"].qty == 100 and res.holdings["WXYZ3"].avg == D("10")  # stock untouched (§2)
    apr = assess(build_ledger(txns, S))[-1]
    assert apr.result["day"] == 0 and apr.tax_total == 0


def test_day_trade_taxed_20_and_irrf_1_percent_estimated() -> None:
    txns = [T(2, "2024-05-02", "BUY", "WXYZ3", "100", "10"), T(3, "2024-05-02", "SELL", "WXYZ3", "100", "15")]
    m = assess(build_ledger(txns, S))[0]
    assert m.tax["day"] == D("100.00") and m.irrf_month == D("5.00") and m.irrf_estimated
    assert m.darf == D("95.00")


def test_loss_carry_forward_across_months_and_pools() -> None:
    txns = [
        T(2, "2024-01-02", "BUY", "BOVA11", "100", "100"),
        T(3, "2024-01-20", "SELL", "BOVA11", "100", "80"),
        T(4, "2024-02-02", "BUY", "HGLG11", "10", "100"),
        T(5, "2024-02-20", "SELL", "HGLG11", "10", "150"),
        T(6, "2024-03-02", "BUY", "BOVA11", "100", "100"),
        T(7, "2024-03-20", "SELL", "BOVA11", "100", "130"),
    ]
    ms = assess(build_ledger(txns, S))
    assert ms[0].loss_carry["common"] == D("-2000")
    assert ms[1].tax["fii"] == D("100.00") and ms[1].loss_carry["common"] == D("-2000")  # FII does not use it
    assert ms[2].tax["common"] == D("150.00") and ms[2].loss_carry["common"] == 0  # (3,000 - 2,000) x 15 %


def test_small_darf_carried() -> None:
    txns = [
        T(2, "2024-01-02", "BUY", "BOVA11", "10", "10"),
        T(3, "2024-01-20", "SELL", "BOVA11", "10", "15"),
        T(4, "2024-02-02", "BUY", "BOVA11", "100", "10"),
        T(5, "2024-02-20", "SELL", "BOVA11", "100", "15"),
    ]
    ms = assess(build_ledger(txns, S))
    assert ms[0].darf == 0 and ms[0].darf_carry == D("7.50")
    assert ms[1].darf == D("82.50")  # 75.00 + 7.50


def test_due_date_last_business_day_next_month() -> None:
    days = [date(2024, 3, d) for d in range(1, 32)]
    business = tuple(d for d in days if d.weekday() < 5 and d != date(2024, 3, 29))  # Good Friday
    cal = Calendar(date(2024, 3, 1), date(2024, 3, 31), "t", business)
    txns = [T(2, "2024-01-10", "BUY", "WXYZ3", "1000", "50"), T(3, "2024-02-26", "SELL", "WXYZ3", "1000", "60")]
    assert assess(build_ledger(txns, S), calendar=cal)[-1].due == date(2024, 3, 28)


def test_split_and_reverse_split_keep_cost() -> None:
    txns = [T(2, "2024-01-02", "BUY", "WXYZ3", "100", "30")]
    ev = [
        StockEvent("e1", "WXYZ3", "SPLIT", date(2024, 2, 1), 3, 1),
        StockEvent("e2", "WXYZ3", "REVERSE_SPLIT", date(2024, 3, 1), 1, 10),
    ]
    res = build_ledger(txns, S, ev)
    h = res.holdings["WXYZ3"]
    assert h.qty == 30 and h.cost == D("3000") and h.avg == D("100")
    postings_balance(res)


def test_bonus_cost_from_file_and_zero_cost_issue() -> None:
    txns = [T(2, "2024-01-02", "BUY", "WXYZ3", "100", "22"), T(3, "2024-02-01", "BONUS", "WXYZ3", "10", "5.50")]
    ev = [StockEvent("e1", "WXYZ3", "BONUS", date(2024, 2, 1), 11, 10)]
    h = build_ledger(txns, S, ev).holdings["WXYZ3"]
    assert h.qty == 110 and h.cost == D("2255.00")  # 2,200 + 10 x 5.50 (IN RFB 1585/2015 art. 58 §1)
    res = build_ledger(txns[:1], S, ev)
    assert res.holdings["WXYZ3"].qty == 110 and res.holdings["WXYZ3"].cost == D("2200")
    assert any("bonificação" in i for i in res.issues)


def test_fraction_reported() -> None:
    res = build_ledger([T(2, "2024-01-02", "BUY", "WXYZ3", "15", "10")], S,
                       [StockEvent("e", "WXYZ3", "REVERSE_SPLIT", date(2024, 2, 1), 1, 10)])  # fmt: skip
    assert res.holdings["WXYZ3"].qty == 1 and any("fração" in i for i in res.issues)


def test_oversell_fails_loudly() -> None:
    with pytest.raises(LedgerError):
        build_ledger([T(2, "2024-01-02", "BUY", "WXYZ3", "10", "10"), T(3, "2024-01-03", "SELL", "WXYZ3", "11", "10")],
                     S)  # fmt: skip


def test_jcp_rate_changes_2026_and_expected_income() -> None:
    txns = [T(2, "2025-01-02", "BUY", "WXYZ3", "1000", "10")]
    ev = [
        CashEvent("j1", "WXYZ3", "JCP", date(2025, 6, 2), date(2025, 6, 20), date(2025, 6, 1), D("0.10")),
        CashEvent("j2", "WXYZ3", "JCP", date(2026, 2, 2), date(2026, 2, 20), date(2026, 2, 1), D("0.10")),
    ]
    res = build_ledger(txns, S, cash_events=ev)
    assert [(i.gross, i.irrf, i.status) for i in res.income] == [(D("100.00"), D("15.00"), "expected"),
                                                                  (D("100.00"), D("17.50"), "expected")]  # fmt: skip
    postings_balance(res)


def test_dividend_monthly_rule_2026() -> None:
    txns = [
        T(2, "2026-01-02", "BUY", "WXYZ3", "100000", "10"),
        T(3, "2026-03-10", "DIVIDEND", "WXYZ3", amount="30000", approved="2026-02-01"),
        T(4, "2026-03-25", "DIVIDEND", "WXYZ3", amount="30000", approved="2026-03-01"),
        T(5, "2026-04-10", "DIVIDEND", "WXYZ3", amount="60000", approved="2025-12-15"),
    ]  # grandfathered (§3 II)
    inc = income_tax(build_ledger(txns, S).income)
    mar, apr = inc
    assert mar.gross == D("60000") and mar.irrf_expected == D("6000.00")
    assert apr.subject == 0 and apr.irrf_expected == 0


def test_tesouro_iof_and_regressive_ir() -> None:
    tk = "Tesouro Selic 2029-03-01"
    txns = [T(2, "2024-01-02", "BUY", tk, "1", "1000"), T(3, "2024-01-12", "SELL", tk, "1", "1010")]
    [r] = build_ledger(txns, {}).realized
    assert r.iof == D("6.60") and r.ir_withheld == D("0.77")  # 66 % of 10 (day 10); 22.5 % of 3.40
    txns = [T(2, "2024-01-02", "BUY", tk, "1", "1000"), T(3, "2026-01-05", "SELL", tk, "1", "1200")]
    [r] = build_ledger(txns, {}).realized
    assert r.iof == 0 and r.ir_withheld == D("30.00")  # > 720 days: 15 %
    assert assess(build_ledger(txns, {}))[-1].darf == 0


def test_rules_versioned_and_referenced() -> None:
    rules = default_rules()
    assert rules.dec("jcp_rate", date(2025, 12, 31)) == D("0.15")
    assert rules.dec("jcp_rate", date(2026, 1, 1)) == D("0.175")
    assert not rules.has("dividend_monthly_rate", date(2025, 12, 31))
    assert all(r.ref for r in rules.rules)
    assert rules.bracket("iof_regressive", date(2024, 1, 1), 30) == 0


def test_rules_overlap_rejected(tmp_path: Path) -> None:
    p = tmp_path / "r.toml"
    p.write_text('[[rule]]\ncode="a"\nvalue="1"\nvt_from=2020-01-01\nref="x"\n'
                 '[[rule]]\ncode="a"\nvalue="2"\nvt_from=2021-01-01\nref="y"\n', encoding="utf-8")  # fmt: skip
    with pytest.raises(ValueError, match="overlap"):
        TaxRules.load(p)


def test_file_load_rejects_bad_rows(tmp_path: Path) -> None:
    p = tmp_path / "t.csv"
    p.write_text("date,kind,ticker,quantity,price,fees\n2024-01-02,BUY,WXYZ3,100,10.5,1\n"
                 "2024-01-03,BUY,WXYZ3,100,\"10,5\",1\n2024-01-04,HOLD,WXYZ3,1,1,0\n", encoding="utf-8")  # fmt: skip
    ld = load(p)
    assert len(ld.txns) == 1 and [r[0] for r in ld.rejected] == [3, 4] and len(ld.sha256) == 64


@settings(max_examples=150, deadline=None)
@given(st.lists(st.tuples(st.booleans(), st.integers(1, 50), st.integers(1, 200)), min_size=1, max_size=25),
       st.sampled_from([(2, 1), (3, 1), (1, 2), (1, 5), (10, 1)]))  # fmt: skip
def test_property_quantities_and_cost(ops: list[tuple[bool, int, int]], ratio: tuple[int, int]) -> None:
    """Quantities never go negative (sells are capped to the position), postings balance, and a split or reverse
    split conserves the total cost of the position."""
    txns, held, day = [], 0, 0
    for i, (is_buy, q, p) in enumerate(ops):
        day += 1
        d = date(2024, 1, 1).toordinal() + day
        if is_buy or held == 0:
            txns.append(Txn(i + 2, date.fromordinal(d), "BUY", "WXYZ3", D(q), D(p), broker="X"))
            held += q
        else:
            q = min(q, held)
            txns.append(Txn(i + 2, date.fromordinal(d), "SELL", "WXYZ3", D(q), D(p), broker="X"))
            held -= q
    res = build_ledger(txns, S)
    assert all(h.quantity >= 0 for h in res.history)
    postings_balance(res)
    h = res.holdings["WXYZ3"]
    before = h.cost
    ev_day = date.fromordinal(date(2024, 1, 1).toordinal() + day + 1)
    res2 = build_ledger(txns, S, [StockEvent("e", "WXYZ3", "SPLIT", ev_day, *ratio)])
    assert res2.holdings["WXYZ3"].cost == before
