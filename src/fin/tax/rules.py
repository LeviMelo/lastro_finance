"""Tax rules as data (PLAN §5): `rules.toml` rows with a validity range and a legal reference, read by date.

A rule changes by adding a row with a new `vt_from` (and closing the old one with `vt_to`), never by a code branch.
`docs/sources/tax_rules.md` records where each text was read.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from functools import cache
from itertools import pairwise
from pathlib import Path

RULES_FILE = Path(__file__).with_name("rules.toml")


class RuleNotFound(LookupError):
    """No rule row of this code is in force on the date: the engine must not guess one."""


@dataclass(frozen=True)
class TaxRule:
    code: str
    vt_from: date
    vt_to: date | None
    ref: str
    value: str | None = None
    brackets: tuple[tuple[int, Decimal], ...] = ()

    def in_force(self, d: date) -> bool:
        return self.vt_from <= d and (self.vt_to is None or d <= self.vt_to)


@dataclass(frozen=True)
class TaxRules:
    rules: tuple[TaxRule, ...]

    @classmethod
    def load(cls, path: Path = RULES_FILE) -> TaxRules:
        doc = tomllib.loads(path.read_text(encoding="utf-8"))
        out = []
        for r in doc["rule"]:
            br = tuple((int(n), Decimal(v)) for n, v in r.get("brackets", []))
            out.append(TaxRule(r["code"], r["vt_from"], r.get("vt_to"), r["ref"], r.get("value"), br))
        rules = cls(tuple(out))
        rules._check_overlaps()
        return rules

    def _check_overlaps(self) -> None:
        by: dict[str, list[TaxRule]] = {}
        for r in self.rules:
            by.setdefault(r.code, []).append(r)
        for code, rs in by.items():
            rs.sort(key=lambda r: r.vt_from)
            for a, b in pairwise(rs):
                if a.vt_to is None or a.vt_to >= b.vt_from:
                    raise ValueError(f"tax rule {code}: ranges overlap ({a.vt_from}, {b.vt_from})")

    def rule(self, code: str, d: date) -> TaxRule:
        for r in self.rules:
            if r.code == code and r.in_force(d):
                return r
        raise RuleNotFound(f"no tax rule {code!r} in force on {d}")

    def has(self, code: str, d: date) -> bool:
        return any(r.code == code and r.in_force(d) for r in self.rules)

    def dec(self, code: str, d: date) -> Decimal:
        v = self.rule(code, d).value
        if v is None:
            raise RuleNotFound(f"tax rule {code!r} has no scalar value")
        return Decimal(v)

    def text(self, code: str, d: date) -> str:
        v = self.rule(code, d).value
        if v is None:
            raise RuleNotFound(f"tax rule {code!r} has no scalar value")
        return v

    def bracket(self, code: str, d: date, n: int) -> Decimal:
        """The rate of the first bracket whose upper bound (inclusive) is at least `n`."""
        for upto, rate in self.rule(code, d).brackets:
            if n <= upto:
                return rate
        raise RuleNotFound(f"tax rule {code!r}: {n} is beyond the last bracket")


@cache
def default_rules() -> TaxRules:
    return TaxRules.load()
