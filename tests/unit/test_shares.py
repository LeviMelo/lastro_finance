"""The unit of CVM share counts is inferred per filing: anchored to B3 today, toggled by a ~1,000x jump."""

from __future__ import annotations

from fin.core.shares import infer_units


def test_anchor_and_switch() -> None:
    # Bradesco: thousands until 2023, units from 2024 (2026-11-07 measurement)
    counts = [8_870_213, 9_719_079, 10_642_170, 10_642_170_228, 10_592_012_028]
    assert infer_units(counts, anchor=11_196_864_781) == [1000, 1000, 1000, 1, 1]


def test_thousands_throughout_and_unknown_anchor() -> None:
    assert infer_units([9_804_135, 11_026_869], anchor=11_026_869_192) == [1000, 1000]
    assert infer_units([5, 6], anchor=None) == [None, None]
    assert infer_units([5_000_000], anchor=99) == [None]  # neither unit near B3's count
