## ADR-0033: The ledger runs on a transactions file; tax rules are dated data with their legal reference

**Date:** 2026-11-09. **Status:** active. `ledger/` (`fin ledger`), `tax/` (`fin tax`), `tax/rules.toml`.

**Context.** Stage I (PLAN §5) must work for an owner with no investments yet. It therefore cannot wait for broker
notes or B3's investor-portal exports. The tax rules changed in 2026: JCP withholding is 17.5 % (LC 224/2025), and
dividends above R$ 50,000 a month from one payer are withheld at 10 % (Lei 15.270/2025). MP 1.303/2025, which would
have unified the rates, lapsed. The texts read are in `docs/sources/tax_rules.md`.

**Decision.**
- **Input.** One CSV (`inbox/transactions.csv` by default; layout in `ledger/transactions.py`) of trades, bonuses,
  transfers and cash events, with fees and the IRRF the broker reported. A broker note or B3 export is converted
  into it, never parsed into the ledger directly. The file is stored in raw, and every output row carries its
  SHA-256 and line.
- **Ledger.**
  - Average cost per asset for the taxpayer (IN RFB 1585/2015 art. 58); quantities are also kept per broker.
  - Day trade per day, broker and asset, the first buy paired with the first sell (art. 65).
  - Double-entry postings that sum to zero per transaction.
  - Tesouro Direto in lots, FIFO, with the regressive IR and the IOF.
- **Corporate events from core.**
  - Splits and reverse splits keep the total cost; fractions are reported as issues.
  - A bonus takes the cost from the file's BONUS row (art. 58 §1). Without one, the shares enter at zero cost, with
    an issue.
  - Cash events of held assets become `expected` income rows unless the file reports them.
- **Tax.**
  - Monthly IR per pool: common 15 % with the R$ 20,000 stock-sales exemption; day trade 20 %; FII/Fiagro 20 %.
  - Losses carry forward within their pool; IRRF is deducted and carried; a DARF under R$ 10 is carried.
  - DARF 6015 is due on the last ANBIMA business day of the next month.
  - Fixed-income ETFs and Tesouro are taxed at source: reported, not put in the DARF.
- **Rules as data.** Each `rules.toml` row has a code, a value or brackets, `vt_from`/`vt_to` and the legal
  reference. Overlapping ranges are rejected, and a missing rule raises instead of being guessed.
- **Engineering defaults.**
  - Cents are rounded half-up.
  - Units are taxed like stocks but without the exemption, until a Receita ruling on units is read.
  - Crypto ETFs and ETF-FII quotas are taxed like equity ETFs (not verified).
  - FII income is exempt without checking the fund's 100-holder and 10 % conditions.
  - A dividend with no approval date is treated as subject to the 2026 rule.

**Not built.** Come-cotas, crypto held directly, offshore holdings (Lei 14.754/2023), the annual IRPF minimum tax
of Lei 15.270, options, futures and short sales; also the reconciliation against B3's investor-portal export,
which needs a real export.

**Verified.** 19 tests (`tests/unit/test_ledger_tax.py`):
- the Receita worked example: gain 9,967.00, tax 1,495.05, DARF 1,492.05;
- the exemption edge, at exactly R$ 20,000.00 and at 20,010;
- day-trade pairing, IRRF and loss carry across pools;
- splits, bonuses and fractions; the 2026 JCP and dividend rules; Tesouro IOF and regressive IR;
- Hypothesis checks of non-negative quantities, balanced postings and cost conserved across splits.

**Would overturn it.** A real broker-note or B3-export layout that carries what the CSV cannot, or a Receita
ruling that contradicts one of the defaults above.
