"""Fund lineage across CVM Resolution 175 (PLAN §4.10; ADR-0025).

Under Res. 175 a legacy fund (keyed by its CNPJ) was *adapted*: the register now holds a fund (`ID_Registro_Fundo`,
`CNPJ_Fundo`, `Data_Adaptacao_RCVM175`) with one or more classes (`ID_Registro_Classe`, `CNPJ_Classe`) and optional
subclasses. The daily report (informe diário) then publishes the class under `CNPJ_FUNDO_CLASSE`, with
`TP_FUNDO_CLASSE` = `CLASSES - FIF` (or `CLASSE FIF/FAPI`) in place of the legacy type, and the quota series goes on.

**Bridging rule.** `core.fund_lineage` has one row per class that has a legacy predecessor, the predecessor being a
CNPJ present in the legacy register (staging `fund`, or `fund_history`):
- `same_cnpj`: the class CNPJ equals the fund CNPJ and the legacy register knows it. The register keeps the CNPJ
  through the adaptation; the class is the same legal entity under a new type (37,653 of 37,803 classes of adapted
  funds share their fund's CNPJ).
- `class_own_legacy`: the class CNPJ differs from the fund's, but is itself a legacy CNPJ: an existing legacy fund
  that became a class of another (umbrella) fund. The predecessor is the class CNPJ.
- `fund_single_class`: the class CNPJ is new, the fund has exactly this class and the fund CNPJ is a legacy CNPJ: the
  fund's legacy quota series is the class's. The predecessor is the fund CNPJ.
- `fund_multi_class`: the class CNPJ is new, the fund has several classes and its CNPJ is a legacy one. The legacy
  fund was split: no class is *the* continuation, so the rows are listed but not claimed continuous.
A class with no legacy CNPJ is a new fund under Res. 175 (`Data_Adaptacao_RCVM175` is filled for those too) and has no
row. `valid_from` is the register's `Data_Adaptacao_RCVM175`; the daily report switches type a median of 17
days later (`bridge_check` measures the actual switch from the data).

**`bridge_check`** tests the claim on the daily series: the class's first class-typed row (`F`) against the last
legacy-typed row before it (`L`) of the predecessor. A bridge is `clean` when the business days strictly between `L`
and `F` (ANBIMA calendar) are at most `MAX_GAP_BD` and the quota moves at most `MAX_JUMP` (1 %) from `L` to `F`;
otherwise `moved` (above 1 % but within `MAX_SIGMAS` of the fund's own robust daily sigma: an ordinary
day), `jump` (above both), `gap`, or `no_legacy_series` / `no_class_series` where a side has no rows. A class
published only per subclass is tested on each subclass and keeps the one closest to the legacy quota (`via_subclass`).
"""

from __future__ import annotations

from datetime import date, timedelta

import polars as pl

from fin.config import Zones
from fin.reference.calendar import Calendar, CalendarRangeError
from fin.schema import Column, Contract
from fin.store.runs import IngestRun
from fin.store.tables import read_parquet_dir, write_parquet

MAX_JUMP = 0.01  # |quota(F) / quota(L) - 1| for a clean bridge
MAX_GAP_BD = 3  # business days with no report between L and F
MAX_SIGMAS = 5  # a move above MAX_JUMP is `moved` (an ordinary day for that fund) up to this many of its own sigmas

LINEAGE = Contract(
    table="core.fund_lineage",
    version=1,
    description="A CVM 175 class and the legacy CNPJ whose history it continues, with the rule that links them.",
    columns=(
        Column("class_id", pl.String, "ID_Registro_Classe", "id do registro da classe", nullable=False),
        Column("class_cnpj", pl.String, "CNPJ_Classe, 14 digits", "CNPJ da classe", nullable=False),
        Column(
            "predecessor_cnpj",
            pl.String,
            "legacy fund CNPJ continued by the class, 14 digits",
            "CNPJ antecessor",
            nullable=False,
        ),
        Column(
            "fund_id", pl.String, "ID_Registro_Fundo of the class's fund", "id do registro do fundo", nullable=False
        ),
        Column("fund_cnpj", pl.String, "CNPJ_Fundo, 14 digits", "CNPJ do fundo", nullable=False),
        Column("valid_from", pl.Date, "Data_Adaptacao_RCVM175", "adaptação à RCVM 175", "date"),
        Column(
            "method",
            pl.String,
            "same_cnpj, class_own_legacy, fund_single_class or fund_multi_class",
            "regra",
            nullable=False,
        ),
        Column(
            "classes_in_fund",
            pl.Int32,
            "classes the fund has in the register",
            "classes do fundo",
            "count",
            nullable=False,
        ),
    ),
    key=("class_id", "predecessor_cnpj"),
)

CONTINUOUS = ("same_cnpj", "class_own_legacy", "fund_single_class")  # methods that claim the same quota series


def _latest(df: pl.DataFrame, key: str) -> pl.DataFrame:
    """The newest version of each row (staging keeps changed rows only: the latest run wins)."""
    return df.sort("ingest_run_id").unique(key, keep="last", maintain_order=True)


def legacy_cnpjs(zones: Zones) -> set[str]:
    cnpjs: set[str] = set()
    fund = read_parquet_dir(zones.staging / "cvm_fi_cadastro" / "fund")
    if fund is not None:
        cnpjs |= set(fund["cnpj"].to_list())
    hist = read_parquet_dir(zones.staging / "cvm_fi_cadastro" / "fund_history")
    if hist is not None:
        cnpjs |= set(hist["cnpj"].unique().to_list())
    return cnpjs


def lineage(funds: pl.DataFrame, classes: pl.DataFrame, legacy: set[str]) -> pl.DataFrame:
    """`funds` and `classes` are the staging frames (latest versions); `legacy` the CNPJs of the legacy register."""
    n = classes.group_by("fund_id").len().rename({"len": "classes_in_fund"})
    j = (
        classes.select(
            "class_id", pl.col("cnpj").alias("class_cnpj"), "fund_id", "raw_sha256", "raw_locator", "ingest_run_id"
        )
        .join(
            funds.select("fund_id", pl.col("cnpj").alias("fund_cnpj"), pl.col("adapted_on").alias("valid_from")),
            on="fund_id",
        )
        .join(n, on="fund_id")
        .with_columns(
            pl.col("class_cnpj").is_in(list(legacy)).alias("own"),
            pl.col("fund_cnpj").is_in(list(legacy)).alias("fund_legacy"),
        )
    )
    same = pl.col("class_cnpj") == pl.col("fund_cnpj")
    method = (
        pl.when(pl.col("own") & same)
        .then(pl.lit("same_cnpj"))
        .when(pl.col("own"))
        .then(pl.lit("class_own_legacy"))
        .when(pl.col("fund_legacy") & (pl.col("classes_in_fund") == 1))
        .then(pl.lit("fund_single_class"))
        .when(pl.col("fund_legacy"))
        .then(pl.lit("fund_multi_class"))
    )
    return (
        j.with_columns(method.alias("method"))
        .filter(pl.col("method").is_not_null())
        .with_columns(
            pl.when(pl.col("method").is_in(["same_cnpj", "class_own_legacy"]))
            .then(pl.col("class_cnpj"))
            .otherwise(pl.col("fund_cnpj"))
            .alias("predecessor_cnpj"),
            pl.col("classes_in_fund").cast(pl.Int32),
        )
        .select(*LINEAGE.names)
    )


def build(zones: Zones, run: IngestRun | None = None) -> dict[str, int]:
    base = zones.staging / "cvm_fi_cadastro"
    funds, classes = read_parquet_dir(base / "registered_fund"), read_parquet_dir(base / "registered_class")
    if funds is None or classes is None:
        return {}
    lin = lineage(_latest(funds, "fund_id"), _latest(classes, "class_id"), legacy_cnpjs(zones))
    good, bad = LINEAGE.split(lin)
    write_parquet(good.sort("class_id", "predecessor_cnpj"), zones.core / "fund_lineage" / "fund_lineage.parquet")
    if run is not None:
        run.count("core.fund_lineage", in_=lin.height, out=good.height, quarantined=bad.height)
    return {"fund_lineage": good.height, "fund_lineage:quarantined": bad.height}


# ------------------------------------------------------------------------------------------------ bridging test
def load_daily(zones: Zones, lin: pl.DataFrame) -> pl.DataFrame:
    """The informe diário rows `bridge_check` needs: the lineage's CNPJs from 90 days before the first adaptation, the
    latest version of each (cnpj, subclass, date) (staging keeps the versions CVM re-sent)."""
    since = lin["valid_from"].min() - timedelta(days=90)  # type: ignore[operator]
    cnpjs = pl.concat([lin["class_cnpj"], lin["predecessor_cnpj"]]).unique().to_list()
    d = (
        pl.scan_parquet(str(zones.staging / "cvm_fi_inf_diario" / "daily" / "**" / "*.parquet"))
        .select(
            pl.col("cnpj").str.replace_all(r"\D", ""),
            "fund_type",
            pl.col("subclass_id").fill_null(""),
            "reference_date",
            "quota_value_brl",
            "ingest_run_id",
        )
        .filter((pl.col("reference_date") >= since) & pl.col("cnpj").is_in(cnpjs))
        .collect()
    )
    return d.sort("ingest_run_id").unique(["cnpj", "subclass_id", "reference_date"], keep="last").drop("ingest_run_id")


def _gap_bd(cal: Calendar, last: date, first: date) -> int | None:
    try:
        return max(cal.du(last, first) - 1, 0)
    except CalendarRangeError:
        return None


def bridge_check(lin: pl.DataFrame, daily: pl.DataFrame, cal: Calendar) -> pl.DataFrame:
    """One row per lineage row: how the class's daily quota series continues the predecessor's.

    `daily` has `cnpj` (14 digits), `fund_type`, `subclass_id`, `reference_date`, `quota_value_brl`, one row per
    (cnpj, subclass_id, reference_date). A row is legacy-typed unless its `fund_type` starts with `CLASSE`.
    """
    d = (
        daily.filter(pl.col("quota_value_brl") > 0)
        .with_columns(
            pl.col("subclass_id").fill_null(""),
            pl.col("fund_type").fill_null("").str.starts_with("CLASSE").alias("is_class"),
        )
        .select(
            "cnpj", "subclass_id", "reference_date", pl.col("quota_value_brl").cast(pl.Float64).alias("q"), "is_class"
        )
    )
    leg = d.filter(~pl.col("is_class") & (pl.col("subclass_id") == "")).sort("cnpj", "reference_date")
    ret = leg.with_columns((pl.col("q") / pl.col("q").shift(1).over("cnpj") - 1).alias("ret"))
    # the fund's own daily move: robust sigma (1.4826 x MAD) of its legacy daily returns
    sigma = ret.group_by("cnpj").agg((1.4826 * (pl.col("ret") - pl.col("ret").median()).abs().median()).alias("sigma"))
    legacy = leg.join(sigma, on="cnpj").select(
        pl.col("cnpj").alias("predecessor_cnpj"),
        pl.col("reference_date").alias("last_legacy"),
        pl.col("q").alias("q_before"),
        pl.col("sigma").fill_null(0.0),
    )
    klass = (
        d.filter(pl.col("is_class"))
        .sort("reference_date")
        .group_by("cnpj", "subclass_id")
        .agg(pl.col("reference_date").first().alias("first_class"), pl.col("q").first().alias("q_after"))
    )
    # class-level series when the class has one, else its subclasses
    has_class_level = (
        klass.filter(pl.col("subclass_id") == "").select("cnpj").unique().with_columns(pl.lit(True).alias("lvl"))
    )
    klass = (
        klass.join(has_class_level, on="cnpj", how="left")
        .filter((pl.col("subclass_id") == "") | pl.col("lvl").is_null())
        .with_columns((pl.col("subclass_id") != "").alias("via_subclass"))
        .drop("lvl")
    )
    cand = lin.join(klass, left_on="class_cnpj", right_on="cnpj", how="left")
    cand = cand.sort("first_class")
    pair = cand.filter(pl.col("first_class").is_not_null()).join_asof(
        legacy.sort("last_legacy"),
        left_on="first_class",
        right_on="last_legacy",
        by_left="predecessor_cnpj",
        by_right="predecessor_cnpj",
        strategy="backward",
        allow_exact_matches=False,
        check_sortedness=False,
    )
    pair = pair.with_columns((pl.col("q_after") / pl.col("q_before") - 1).abs().alias("jump"))
    # one candidate per lineage row: the subclass closest to the legacy quota (the class-level series if it exists)
    best = pair.sort("jump", nulls_last=True).unique(
        ["class_id", "predecessor_cnpj"], keep="first", maintain_order=True
    )
    out = lin.join(
        best.select(
            "class_id",
            "predecessor_cnpj",
            "last_legacy",
            "first_class",
            "q_before",
            "q_after",
            "jump",
            "sigma",
            "via_subclass",
        ),
        on=["class_id", "predecessor_cnpj"],
        how="left",
    )
    rows = out.to_dicts()
    for r in rows:
        r["gap_bd"] = (
            _gap_bd(cal, r["last_legacy"], r["first_class"]) if r["last_legacy"] and r["first_class"] else None
        )
    out = pl.DataFrame(rows, schema={**out.schema, "gap_bd": pl.Int64})
    status = (
        pl.when(pl.col("first_class").is_null())
        .then(pl.lit("no_class_series"))
        .when(pl.col("last_legacy").is_null())
        .then(pl.lit("no_legacy_series"))
        .when(pl.col("gap_bd").is_null() | (pl.col("gap_bd") > MAX_GAP_BD))
        .then(pl.lit("gap"))
        .when(pl.col("jump") <= MAX_JUMP)
        .then(pl.lit("clean"))
        .when(pl.col("jump") <= MAX_SIGMAS * pl.col("sigma"))
        .then(pl.lit("moved"))
        .otherwise(pl.lit("jump"))
    )
    return out.with_columns(status.alias("status"))
