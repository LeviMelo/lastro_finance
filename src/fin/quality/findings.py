"""Data-quality findings (PLAN §4.11.5; invariant 7: reconcile, don't trust; ADR-0022).

Each check is a pure function of the zones that returns the disagreements it finds. `run` writes one Parquet file per
check under `quality/dq_finding/` (rebuildable, deterministic: no wall-clock time in a row). A finding's id is a
hash of (check, entity, valid date), so it is stable across rebuilds. Its review status lives in
`quality/resolutions.toml`, in git: an open finding is one nobody has looked at, and a decision about one is code.

Checks:
- `vna_ntnb_vs_ipca`: Tesouro's NTN-B VNA vs trunc(1000 x IPCA index(m-1) / 1614.62, 6 dp) from IBGE's index;
- `share_count_unit_mismatch`: FRE (whole shares) vs the nearest DFP/ITR count, off by a factor near 1,000;
- `link_price_jump`: a ticker or name continuity link whose price ratio is outside [0.5, 2] with no stock event
  on either line within 10 days;
- `stock_event_unproven`: a stock event no second source, filing or price move confirms (status `candidate`);
- `ohlc_inconsistent`: a standard-lot session whose high or low does not bound its open and close, or with a
  non-positive price (`error`: it breaks every return through it). The average (PREMED) is not checked: it lies
  outside high/low on 6,520 sessions (1989-91 and, from 2021, mostly BDRs), so it includes trades the high/low do
  not (docs/sources/b3_cotahist.md).
"""

from __future__ import annotations

import hashlib
import tomllib
from collections.abc import Callable
from decimal import ROUND_DOWN, Decimal
from pathlib import Path

import polars as pl

from fin.config import Zones
from fin.schema import Column, Contract
from fin.store.runs import IngestRun
from fin.store.tables import read_parquet_dir, write_parquet

RESOLUTIONS = Path(__file__).with_name("resolutions.toml")
SEVERITIES = ("info", "warn", "error", "blocker")

DQ_FINDING = Contract(
    table="quality.dq_finding",
    version=1,
    description="A disagreement between sources, or with a rule, found by a named check.",
    provenance=False,
    columns=(
        Column("finding_id", pl.String, "F + 12 hex of sha256(check|entity|vt)", "id", nullable=False),
        Column("check_id", pl.String, "the check that found it", "verificação", nullable=False),
        Column("severity", pl.String, "info, warn, error or blocker", "gravidade", nullable=False),
        Column("entity_kind", pl.String, "series, instrument, issuer or link", "tipo de entidade", nullable=False),
        Column(
            "entity_id", pl.String, "the entity's id (series_id, instrument_id, CNPJ...)", "entidade", nullable=False
        ),
        Column("vt", pl.Date, "valid date the finding is about", "data", "date"),
        Column("observed", pl.String, "the value found", "observado"),
        Column("expected", pl.String, "the value the rule or the other source gives", "esperado"),
        Column("detail", pl.String, "what disagrees, in a sentence", "detalhe", nullable=False),
        Column("evidence", pl.String, "the rows it rests on (series@date, table keys, raw locators)", "evidência"),
        Column(
            "status",
            pl.String,
            "open, acknowledged, resolved or wont_fix (resolutions.toml)",
            "situação",
            nullable=False,
        ),
        Column("resolution_note", pl.String, "the reviewer's note", "nota de resolução"),
    ),
    key=("finding_id",),
)
COLS = [c.name for c in DQ_FINDING.columns if c.name not in ("finding_id", "status", "resolution_note")]


def finding_id(check: str, entity: str, vt: object) -> str:
    return "F" + hashlib.sha256(f"{check}|{entity}|{vt}".encode()).hexdigest()[:12]


def _frame(rows: list[dict[str, object]]) -> pl.DataFrame:
    schema = {c.name: c.dtype for c in DQ_FINDING.columns if c.name in COLS}
    return pl.DataFrame(rows, schema=schema) if rows else pl.DataFrame(schema=schema)


def _series(zones: Zones, *ids: str) -> pl.DataFrame:
    path = zones.core / "series_observation"
    if not path.exists():
        return pl.DataFrame(schema={"series_id": pl.String, "vt_reference": pl.String, "value": pl.Decimal(38, 24)})
    return (
        pl.scan_parquet(path / "*.parquet")
        .filter(pl.col("series_id").is_in(ids))
        .select("series_id", "vt_reference", "value")
        .collect()
    )


IPCA_JUN_2000 = Decimal("1614.62")


def vna_ntnb_vs_ipca(zones: Zones) -> pl.DataFrame:
    s = _series(zones, "tesouro_vna:NTN-B", "ibge_sidra:1737/v2266")
    ipca = {r["vt_reference"]: r["value"] for r in s.filter(pl.col("series_id") != "tesouro_vna:NTN-B").to_dicts()}
    rows: list[dict[str, object]] = []
    for r in s.filter(pl.col("series_id") == "tesouro_vna:NTN-B").sort("vt_reference").to_dicts():
        y, m = int(r["vt_reference"][:4]), int(r["vt_reference"][5:7])
        prev = f"{y - (m == 1)}-{(m - 2) % 12 + 1:02d}"
        if prev not in ipca:
            continue
        rule = (1000 * Decimal(ipca[prev]) / IPCA_JUN_2000).quantize(Decimal("0.000001"), rounding=ROUND_DOWN)
        got = Decimal(r["value"]).quantize(Decimal("0.000001"))
        if got != rule:
            implied = got * IPCA_JUN_2000 / 1000
            rows.append(
                {
                    "check_id": "vna_ntnb_vs_ipca",
                    "severity": "warn",
                    "entity_kind": "series",
                    "entity_id": "tesouro_vna:NTN-B",
                    "vt": pl.Series([r["vt_reference"]]).str.to_date()[0],
                    "observed": str(got),
                    "expected": str(rule),
                    "detail": f"VNA implies an IPCA index of {implied:.4f} for {prev}; IBGE gives {ipca[prev]:.2f}",
                    "evidence": f"tesouro_vna:NTN-B@{r['vt_reference']}; ibge_sidra:1737/v2266@{prev}",
                }
            )
    return _frame(rows)


def share_count_unit_mismatch(zones: Zones) -> pl.DataFrame:
    p = zones.core / "share_count" / "share_count.parquet"
    if not p.exists():
        return _frame([])
    sc = pl.read_parquet(p).filter(pl.col("unit").is_not_null() & (pl.col("total") > 0))
    fre = sc.filter(pl.col("form") == "fre").sort("received_on")
    cvm = sc.filter(pl.col("form") != "fre").sort("received_on")
    j = fre.join_asof(
        cvm.select(
            "issuer_cnpj",
            "received_on",
            pl.col("total").alias("t2"),
            pl.col("form").alias("f2"),
            pl.col("reference_date").alias("r2"),
            pl.col("unit").alias("u2"),
        ),
        on="received_on",
        by="issuer_cnpj",
        strategy="nearest",
        tolerance="120d",
        check_sortedness=False,
    ).filter(pl.col("t2").is_not_null())
    r = pl.col("t2") / pl.col("total")
    j = j.filter(r.is_between(1 / 3000, 1 / 300) | r.is_between(300, 3000))
    return j.select(
        pl.lit("share_count_unit_mismatch").alias("check_id"),
        pl.lit("warn").alias("severity"),
        pl.lit("issuer").alias("entity_kind"),
        pl.col("issuer_cnpj").alias("entity_id"),
        pl.col("r2").alias("vt"),
        pl.col("t2").cast(pl.String).alias("observed"),
        pl.col("total").cast(pl.String).alias("expected"),
        pl.format(
            "{} {} total read with unit {} disagrees with the FRE delivered {} by a factor near 1,000",
            "f2",
            "r2",
            "u2",
            "received_on",
        ).alias("detail"),
        pl.format("share_count {}/{}; share_count fre/{}", "f2", "r2", "received_on").alias("evidence"),
    )


def link_price_jump(zones: Zones) -> pl.DataFrame:
    p = zones.core / "instrument_link" / "instrument_link.parquet"
    if not p.exists():
        return _frame([])
    links = pl.read_parquet(p).filter(
        pl.col("kind").is_in(["ticker_continuity", "name_continuity"]) & ~pl.col("price_ratio").is_between(0.5, 2.0)
    )
    ev = read_parquet_dir(zones.core / "corporate_event")
    if ev is not None and links.height:
        stock = ev.filter(pl.col("ratio_num").is_not_null()).select("instrument_id", "ex_date")
        near = (
            pl.concat(
                [
                    links.join(stock, left_on="from_instrument_id", right_on="instrument_id"),
                    links.join(stock, left_on="to_instrument_id", right_on="instrument_id"),
                ]
            )
            .filter((pl.col("ex_date") - pl.col("link_date")).dt.total_days().abs() <= 10)
            .select("from_instrument_id", "to_instrument_id", "link_date")
            .unique()
        )
        links = links.join(near, on=["from_instrument_id", "to_instrument_id", "link_date"], how="anti")
    return links.select(
        pl.lit("link_price_jump").alias("check_id"),
        pl.lit("warn").alias("severity"),
        pl.lit("link").alias("entity_kind"),
        pl.format("{}>{}", "from_instrument_id", "to_instrument_id").alias("entity_id"),
        pl.col("link_date").alias("vt"),
        pl.col("price_ratio").round(6).cast(pl.String).alias("observed"),
        pl.lit("0.5 to 2, or a stock event within 10 days").alias("expected"),
        pl.format(
            "{} link to {}: the price changes by a factor of {} with no stock event",
            "kind",
            "ticker",
            pl.col("price_ratio").round(4),
        ).alias("detail"),
        pl.format("instrument_link {}>{}@{}", "from_instrument_id", "to_instrument_id", "link_date").alias("evidence"),
    )


def stock_event_unproven(zones: Zones) -> pl.DataFrame:
    ev = read_parquet_dir(zones.core / "corporate_event")
    if ev is None:
        return _frame([])
    c = ev.filter((pl.col("status") == "candidate") & pl.col("ratio_num").is_not_null())
    return c.select(
        pl.lit("stock_event_unproven").alias("check_id"),
        pl.lit("info").alias("severity"),
        pl.lit("instrument").alias("entity_kind"),
        pl.format("{}:{}:{}/{}", "instrument_id", "event_type", "ratio_num", "ratio_den").alias("entity_id"),
        pl.col("ex_date").alias("vt"),
        pl.col("price_check").round(4).cast(pl.String).alias("observed"),
        pl.lit("price_check near 1, a second source or an IPE filing").alias("expected"),
        pl.format(
            "{} {}:{} reported by {} only; it adjusts nothing", "event_type", "ratio_num", "ratio_den", "sources"
        ).alias("detail"),
        pl.format("corporate_event {}@{}", "instrument_id", "ex_date").alias("evidence"),
    )


def ohlc_inconsistent(zones: Zones) -> pl.DataFrame:
    path = zones.core / "price_daily"
    if not path.exists():
        return _frame([])
    f = pl.col
    lo, hi = pl.min_horizontal("open", "close"), pl.max_horizontal("open", "close")
    bad = (f("low") <= 0) | (f("high") < hi) | (f("low") > lo)
    df = (
        pl.scan_parquet(path / "*.parquet")
        .filter((f("market_segment") == "lote_padrao") & bad)
        .select("instrument_id", "ticker", "trade_date", "open", "high", "low", "close", "raw_locator")
        .collect()
    )
    return df.select(
        pl.lit("ohlc_inconsistent").alias("check_id"),
        # a non-positive price breaks every return through it
        pl.when(pl.min_horizontal("open", "high", "low", "close") <= 0)
        .then(pl.lit("error"))
        .otherwise(pl.lit("warn"))
        .alias("severity"),
        pl.lit("instrument").alias("entity_kind"),
        "instrument_id",
        "trade_date",
        pl.format("O {} H {} L {} C {}", "open", "high", "low", "close").alias("observed"),
        pl.lit("low <= open, close <= high; prices > 0").alias("expected"),
        pl.format("{}: the high/low do not bound the session as COTAHIST states it", "ticker").alias("detail"),
        "raw_locator",
    ).rename({"instrument_id": "entity_id", "trade_date": "vt", "raw_locator": "evidence"})


CHECKS: dict[str, Callable[[Zones], pl.DataFrame]] = {
    "vna_ntnb_vs_ipca": vna_ntnb_vs_ipca,
    "share_count_unit_mismatch": share_count_unit_mismatch,
    "link_price_jump": link_price_jump,
    "stock_event_unproven": stock_event_unproven,
    "ohlc_inconsistent": ohlc_inconsistent,
}


def resolutions(path: Path = RESOLUTIONS) -> pl.DataFrame:
    data = tomllib.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    rows = [{"finding_id": k, "status": v["status"], "resolution_note": v.get("note")} for k, v in data.items()]
    schema = {"finding_id": pl.String, "status": pl.String, "resolution_note": pl.String}
    return pl.DataFrame(rows, schema=schema) if rows else pl.DataFrame(schema=schema)


def run(
    zones: Zones,
    ingest_run: IngestRun | None = None,
    only: list[str] | None = None,
    resolutions_path: Path = RESOLUTIONS,
) -> dict[str, int]:
    res = resolutions(resolutions_path)
    out: dict[str, int] = {}
    for name, check in CHECKS.items():
        if only and name not in only:
            continue
        df = check(zones).select(COLS)
        df = df.with_columns(
            pl.struct("check_id", "entity_id", "vt")
            .map_elements(lambda s: finding_id(s["check_id"], s["entity_id"], s["vt"]), return_dtype=pl.String)
            .alias("finding_id")
        )
        df = df.join(res, on="finding_id", how="left").with_columns(pl.col("status").fill_null("open"))
        good, bad = DQ_FINDING.split(df.select(DQ_FINDING.names).unique("finding_id").sort("finding_id"))
        write_parquet(good, zones.quality / "dq_finding" / f"{name}.parquet")
        out[name] = good.height
        if ingest_run is not None:
            ingest_run.count(f"quality.{name}", in_=df.height, out=good.height, quarantined=bad.height)
    return out
