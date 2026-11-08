"""Fund lineage and the CVM 175 bridging test (ADR-0025): golden fund from real lines, the rules on small frames."""

from __future__ import annotations

import io
import zipfile
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import polars as pl

from fin.config import Zones
from fin.core import funds
from fin.ingest import cvm_fi_cad, cvm_funds
from fin.reference.calendar import Calendar
from fin.store.tables import write_parquet

FIXTURES = Path(__file__).parents[1] / "fixtures"
FIX = FIXTURES / "cvm_fi_cadastro"
ROW = {"raw_sha256": "a" * 64, "ingest_run_id": "r", "notes": None, "dataset_id": "registro_fundo_classe"}
GOLDEN = "01597187000115"


def _cal() -> Calendar:
    days = pl.DataFrame({"date": pl.date_range(date(2024, 1, 1), date(2025, 12, 31), "1d", eager=True)})
    days = days.with_columns(
        (pl.col("date").dt.weekday() <= 5).alias("is_anbima_business_day"), pl.lit("t").alias("calendar_version")
    )
    return Calendar.from_frame(days)


def _frames(blob: bytes, dataset_id: str) -> dict[str, pl.DataFrame]:
    return {p.dataset_id: p.frame for p in cvm_fi_cad.parse_payload(blob, {**ROW, "dataset_id": dataset_id})}


def _zip(*names: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n in names:
            z.writestr(n, (FIX / n).read_bytes())
    return buf.getvalue()


def _register() -> dict[str, pl.DataFrame]:
    out = _frames(_zip("registro_fundo.csv", "registro_classe.csv", "registro_subclasse.csv"), "registro_fundo_classe")
    out |= _frames(_zip("cad_fi_hist_sit.csv"), "cad_fi_hist")
    out |= _frames((FIX / "cad_fi.csv").read_bytes(), "cad_fi")
    return out


def _legacy(reg: dict[str, pl.DataFrame]) -> set[str]:
    return set(reg["fund"]["cnpj"]) | set(reg["fund_history"]["cnpj"])


def test_lineage_rules_on_real_register_lines() -> None:
    reg = _register()
    lin = funds.lineage(reg["registered_fund"], reg["registered_class"], _legacy(reg))
    assert funds.LINEAGE.split(lin)[1].height == 0
    by_class = {r["class_id"]: r for r in lin.to_dicts()}
    golden = by_class["142"]  # the register keeps the CNPJ: the class is the legacy fund
    assert (golden["method"], golden["predecessor_cnpj"], str(golden["valid_from"])) == (
        "same_cnpj",
        GOLDEN,
        "2024-08-29",
    )
    # an existing legacy fund (own CNPJ) that became one of the three classes of fund 62437
    assert by_class["11938"]["method"] == "class_own_legacy"
    assert by_class["11938"]["predecessor_cnpj"] == "38456821000100" and by_class["11938"]["fund_id"] == "62437"
    assert by_class["11938"]["classes_in_fund"] == 3
    assert lin["raw_sha256"].null_count() == 0  # provenance of the class row


def test_classes_without_a_legacy_cnpj_have_no_lineage() -> None:
    reg = _register()
    assert funds.lineage(reg["registered_fund"], reg["registered_class"], set()).height == 0


def _golden_daily() -> pl.DataFrame:
    frames = []
    for mon in ("202409", "202410"):
        row = {"raw_sha256": "b" * 64, "ingest_run_id": "r", "notes": f"{mon}|inf_diario_fi_{mon}.csv"}
        blob = (FIXTURES / "cvm_fi_inf_diario" / f"inf_diario_fi_{mon}.csv").read_bytes()
        frames += [p.frame for p in cvm_funds.parse_inf_diario(blob, row)]
    return pl.concat(frames).with_columns(pl.col("cnpj").str.replace_all(r"\D", ""))


def test_golden_fund_quota_continues_across_the_switch() -> None:
    reg = _register()
    lin = funds.lineage(reg["registered_fund"], reg["registered_class"], _legacy(reg)).filter(
        pl.col("class_id") == "142"
    )
    r = funds.bridge_check(lin, _golden_daily(), _cal()).row(0, named=True)
    assert r["status"] == "clean" and r["gap_bd"] == 0 and not r["via_subclass"]
    assert (r["last_legacy"], r["first_class"]) == (date(2024, 9, 30), date(2024, 10, 1))
    assert (r["q_before"], r["q_after"]) == (362.546162, 362.69156)  # +0.04 %: one day of an RF DI fund
    assert r["jump"] < 0.001


def _lin(cnpj: str) -> dict[str, Any]:
    return {
        "class_id": cnpj,
        "class_cnpj": cnpj,
        "predecessor_cnpj": cnpj,
        "method": "same_cnpj",
        "valid_from": date(2024, 9, 1),
    }


def _rows(cnpj: str, typ: str, start: date, quotas: list[float], sub: str = "") -> list[dict[str, Any]]:
    out, d = [], start
    for q in quotas:
        while d.weekday() > 4:
            d += timedelta(days=1)
        out.append({"cnpj": cnpj, "fund_type": typ, "subclass_id": sub, "reference_date": d, "quota_value_brl": q})
        d += timedelta(days=1)
    return out


def test_bridge_statuses() -> None:
    leg = [1.0, 1.0004, 1.0008, 1.0012, 1.0016, 1.002]  # five weekdays from Monday 2024-09-02, then Monday 09-09
    ids = {k: f"1000000000000{i}" for i, k in enumerate("abcgnsv", start=1)}
    rows: list[dict[str, Any]] = []
    for k in "acgnv":
        rows += _rows(ids[k], "FI", date(2024, 9, 2), leg)
    rows += _rows(ids["b"], "FI", date(2024, 9, 2), [1.0, 1.02, 1.0, 1.02, 1.0, 1.0])  # an ordinary 2 % a day
    nxt = date(2024, 9, 10)  # the legacy series above ends Monday 09-09; the class starts Tuesday 09-10
    rows += _rows(ids["a"], "CLASSES - FIF", nxt, [1.0024, 1.0028])  # clean: next business day, +0.04 %
    rows += _rows(ids["b"], "CLASSES - FIF", nxt, [1.015, 1.0])  # moved: +1.5 % on a fund that moves 2 %
    rows += _rows(ids["c"], "CLASSES - FIF", nxt, [1.3, 1.3])  # jump: +30 % on a calm fund
    rows += _rows(ids["g"], "CLASSES - FIF", date(2024, 9, 24), [1.0024])  # gap: 10 business days with no report
    rows += _rows(ids["s"], "CLASSES - FIF", nxt, [1.0])  # no legacy series
    # class published per subclass only: the subclass closest to the legacy quota is the continuation
    rows += _rows(ids["v"], "CLASSES - FIF", nxt, [5.0], sub="SUB1") + _rows(
        ids["v"], "CLASSES - FIF", nxt, [1.0025], sub="SUB2"
    )
    schema = {
        "cnpj": pl.String,
        "fund_type": pl.String,
        "subclass_id": pl.String,
        "reference_date": pl.Date,
        "quota_value_brl": pl.Decimal(38, 12),
    }
    daily = pl.DataFrame(rows, schema=schema)
    lin = pl.DataFrame([_lin(ids[k]) for k in "abcgnsv"])
    out = {r["class_id"]: r for r in funds.bridge_check(lin, daily, _cal()).to_dicts()}
    assert {k: out[ids[k]]["status"] for k in "abcgnsv"} == {
        "a": "clean",
        "b": "moved",
        "c": "jump",
        "g": "gap",
        "n": "no_class_series",
        "s": "no_legacy_series",
        "v": "clean",
    }
    assert out[ids["g"]]["gap_bd"] == 10 and out[ids["v"]]["via_subclass"] is True and out[ids["a"]]["gap_bd"] == 0


def test_build_writes_core_lineage(zones: Zones) -> None:
    for ds, frame in _register().items():
        write_parquet(frame, zones.staging / "cvm_fi_cadastro" / ds / "all" / "x.parquet")
    assert funds.build(zones)["fund_lineage"] >= 3
    core = pl.read_parquet(zones.core / "fund_lineage" / "fund_lineage.parquet")
    assert core.schema == pl.Schema({c.name: c.dtype for c in funds.LINEAGE.all_columns})
    assert core.filter(pl.col("class_cnpj") == GOLDEN)["method"].to_list() == ["same_cnpj"]
