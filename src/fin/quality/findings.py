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
- `stock_event_unproven`: a stock event no second source, filing or price move confirms (`candidate`, info), or
  whose ratio the price contradicts (`conflicting`, warn); neither adjusts anything;
- `ohlc_inconsistent`: a standard-lot session whose high or low does not bound its open and close, or with a
  non-positive price (`error`: it breaks every return through it). The average (PREMED) is not checked: it lies
  outside high/low on 6,520 sessions (1989-91 and, from 2021, mostly BDRs), so it includes trades the high/low do
  not (docs/sources/b3_cotahist.md);
- `fiagro_duplicate_filing`: a FIAGRO monthly filing listed twice; the later delivery wins;
- `mirror_vs_anbima`: the pyield mirror's bond PUs and rates against our own ANBIMA files on the dates both hold;
- `cotahist_vs_yahoo`: Yahoo's monthly close (split-adjusted) / our split-adjusted close, per line: a shift of more
  than 10 % between the medians of the 6 months before and after is a split one side applies and the other does
  not. Single months are noise: Yahoo's monthly close is often not the month's last close (CEAB3 2024-07).
"""

from __future__ import annotations

import hashlib
import math
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
        pl.lit("acknowledged").alias("status"),
        pl.lit(
            "rule: the link keeps the measured ratio: a merger's exchange ratio (DURA3 -> DTEX3, 2.63) or a real move "
            "across a restructuring (GOLL4 -> GOLL54, 2025); a holding crossing the link converts at it"
        ).alias("resolution_note"),
    )


def stock_event_unproven(zones: Zones) -> pl.DataFrame:
    ev = read_parquet_dir(zones.core / "corporate_event")
    if ev is None:
        return _frame([])
    c = ev.filter(pl.col("status").is_in(["conflicting", "unsupported"]) & pl.col("ratio_num").is_not_null())
    return c.select(
        pl.lit("stock_event_unproven").alias("check_id"),
        # conflicting: reported (often by two sources) but the price did not move by the ratio
        pl.when(pl.col("status") == "conflicting").then(pl.lit("warn")).otherwise(pl.lit("info")).alias("severity"),
        pl.lit("instrument").alias("entity_kind"),
        pl.format("{}:{}:{}/{}", "instrument_id", "event_type", "ratio_num", "ratio_den").alias("entity_id"),
        pl.col("ex_date").alias("vt"),
        pl.col("price_check").round(4).cast(pl.String).alias("observed"),
        pl.lit("price_check near 1, a second source or an IPE filing").alias("expected"),
        pl.format(
            "{} {}:{} ({}) from {}; it adjusts nothing", "event_type", "ratio_num", "ratio_den", "status", "sources"
        ).alias("detail"),
        pl.format("corporate_event {}@{}", "instrument_id", "ex_date").alias("evidence"),
        pl.lit("acknowledged").alias("status"),
        pl.lit(
            "rule: decided in core.corporate_event (ADR-0016): not applied, contradicted by the price or unconfirmed"
        ).alias("resolution_note"),
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


YAHOO_STEP = 0.10  # a level shift of more than 10 % in Yahoo close / our split-adjusted close
YAHOO_WINDOW = 6  # months on each side (medians: Yahoo's monthly close is not always the last session's)


def _yahoo_monthly(zones: Zones) -> pl.DataFrame:
    """Yahoo's monthly closes (split-adjusted, `range=max`) from the latest archived chart of each ticker."""
    import json

    from fin.store.manifest import Manifest
    from fin.store.raw import RawStore

    m = Manifest(zones.manifest).read().filter((pl.col("source_id") == "yahoo_chart") & (pl.col("http_status") == 200))
    m = m.sort("fetched_at").unique("request_key", keep="last")
    raw = RawStore(zones.raw)
    parts: list[pl.DataFrame] = []
    for sha in m["raw_sha256"].to_list():
        res = (json.loads(raw.read(sha)).get("chart") or {}).get("result") or []
        if not res or not res[0].get("timestamp"):
            continue
        r = res[0]
        sym = str(r["meta"]["symbol"]).removesuffix(".SA")
        # bars sit at local midnight; under the old DST (to 2019) the fixed offset puts them at 23:00 the day before
        off = int(r["meta"].get("gmtoffset") or 0)
        close = r["indicators"]["quote"][0].get("close") or []
        parts.append(
            pl.DataFrame(
                {"ts": [ts + off + 43200 for ts in r["timestamp"]][:-1], "y_close": close[:-1]},  # last: partial
                schema={"ts": pl.Int64, "y_close": pl.Float64},
            ).with_columns(pl.lit(sym).alias("ticker"), pl.lit(sha).alias("y_sha"))
        )
    if not parts:
        return pl.DataFrame(schema={"ticker": pl.String, "month": pl.Date, "y_close": pl.Float64, "y_sha": pl.String})
    y = pl.concat(parts).drop_nulls("y_close")
    return y.select(
        "ticker", pl.from_epoch("ts", time_unit="s").dt.date().dt.truncate("1mo").alias("month"), "y_close", "y_sha"
    ).unique(["ticker", "month"], keep="last")


def cotahist_vs_yahoo(zones: Zones) -> pl.DataFrame:
    path, fac = zones.core / "price_daily", zones.derived / "adjustment_factor"
    if not path.exists():
        return _frame([])
    y = _yahoo_monthly(zones)
    if not y.height:
        return _frame([])
    last = (
        pl.scan_parquet(path / "*.parquet")
        .filter(pl.col("market_segment") == "lote_padrao")
        .filter(pl.col("ticker").is_in(y["ticker"].unique().to_list()))
        .select("instrument_id", "ticker", "trade_date", pl.col("close").cast(pl.Float64))
        .with_columns(pl.col("trade_date").dt.truncate("1mo").alias("month"))
        .group_by("instrument_id", "ticker", "month")
        .agg(pl.all().sort_by("trade_date").last())
        .collect()
    )
    if fac.exists():  # our split adjustment to today's basis: the product of later split factors
        f = pl.read_parquet(fac / "*.parquet").select("instrument_id", "ex_date", "split_factor")
        adj = (
            last.join(f, on="instrument_id", how="left")
            .filter(pl.col("ex_date").is_null() | (pl.col("ex_date") > pl.col("trade_date")))
            .group_by("instrument_id", "ticker", "month")
            .agg(pl.col("split_factor").fill_null(1.0).log().sum().exp().alias("k"))
        )
        last = last.join(adj, on=["instrument_id", "ticker", "month"], how="left").with_columns(
            pl.col("k").fill_null(1.0)
        )
    else:
        last = last.with_columns(pl.lit(1.0).alias("k"))
    j = (
        last.join(y, on=["ticker", "month"])
        .filter(pl.col("close") > 0)
        .with_columns((pl.col("y_close") / (pl.col("close") * pl.col("k"))).alias("r"))
        .sort("instrument_id", "ticker", "month")
    )
    return classify_yahoo(zones, level_shifts(j))


def classify_yahoo(zones: Zones, leads: pl.DataFrame) -> pl.DataFrame:
    """Decides each Yahoo lead from our own data (status by rule, reason in `resolution_note`):
    - `acknowledged`, Yahoo lacks one of our applied stock events: one is within 45 days with a ratio within 30 %
      (in log) of the shift;
    - `acknowledged`, Yahoo's monthly close is noise or wrong: our split-adjusted daily series has no one-day move
      of even half the shift in the window (the month before to the month after);
    - `acknowledged` otherwise too: the official price moved and no official source records an event; Yahoo's
      adjustment is tier U and is not promoted (CLAUDE.md), so B3's prices stand. Implied events (core/events.py)
      already took the leads a filing or a 3x move supports."""
    if not leads.height:
        return leads.with_columns(pl.lit(None, dtype=pl.String).alias("status"),
                                  pl.lit(None, dtype=pl.String).alias("resolution_note"))  # fmt: skip
    lead = leads.with_columns(
        pl.col("entity_id").str.split(":").list.first().alias("_i"),
        pl.col("observed").cast(pl.Float64).log().alias("_ls"),
        pl.int_range(pl.len()).alias("_r"),
    )
    ids = lead["_i"].unique().to_list()
    ev = read_parquet_dir(zones.core / "corporate_event")
    explained = pl.DataFrame(schema={"_r": pl.Int64})
    if ev is not None:
        st = ev.filter(
            pl.col("ratio_num").is_not_null() & pl.col("status").is_in(["confirmed", "price_only", "official"])
        ).select(
            pl.col("instrument_id").alias("_i"),
            "ex_date",
            (pl.col("ratio_num").cast(pl.Float64) / pl.col("ratio_den").cast(pl.Float64)).log().alias("_le"),
        )
        explained = (
            lead.join(st, on="_i")
            .filter(
                ((pl.col("ex_date") - pl.col("vt")).dt.total_days().abs() <= 45)
                & ((pl.col("_le").abs() - pl.col("_ls").abs()).abs() <= 0.3 * pl.col("_ls").abs())
            )
            .select(pl.col("_r").cast(pl.Int64))
            .unique()
        )
    path, fac = zones.core / "price_daily", zones.derived / "adjustment_factor"
    brl = pl.col("brl_num").cast(pl.Float64) / pl.col("brl_den").cast(pl.Float64)
    day = (
        pl.scan_parquet(path / "*.parquet")
        .filter((pl.col("market_segment") == "lote_padrao") & pl.col("instrument_id").is_in(ids))
        .select(pl.col("instrument_id").alias("_i"), "trade_date", (pl.col("close").cast(pl.Float64) * brl).alias("c"))
        .sort("_i", "trade_date")
        .with_columns((pl.col("c") / pl.col("c").shift(1)).over("_i").log().alias("lr"))
        .collect()
    )
    if fac.exists():  # the adjusted one-day move: raw move minus the log factor applied that day
        f = pl.read_parquet(fac / "*.parquet").select(
            pl.col("instrument_id").alias("_i"), pl.col("ex_date").alias("trade_date"), "split_factor"
        )
        day = day.join(f, on=["_i", "trade_date"], how="left").with_columns(
            (pl.col("lr") - pl.col("split_factor").fill_null(1.0).log()).alias("lr")
        )
    moved = (
        lead.join(day, on="_i")
        .filter(
            pl.col("trade_date").is_between(
                pl.col("vt").dt.offset_by("-1mo"), pl.col("vt").dt.offset_by("1mo").dt.month_end()
            )
        )
        .group_by("_r")
        .agg((pl.col("lr").abs().max() >= 0.5 * pl.col("_ls").abs().first()).alias("_moved"))
    )
    out = lead.join(moved, on="_r", how="left").with_columns(
        pl.col("_r").is_in(explained["_r"].to_list()).alias("_expl"),
        (pl.col("_ls").abs() < math.log(1.25)).alias("_small"),
    )
    return out.with_columns(
        pl.lit("acknowledged").alias("status"),
        pl.when(pl.col("_expl")).then(pl.lit("rule: Yahoo lacks a stock event we apply (within 45 days, same size)"))
        .when(~pl.col("_moved").fill_null(False))
        .then(pl.lit("rule: our split-adjusted series has no move of half the shift: Yahoo's close is noise or wrong"))
        .when(pl.col("_small"))
        .then(pl.lit("rule: a shift under 25 % (the smallest implied event) lined up with a real market move: noise"))
        .otherwise(pl.lit("rule: the official price moved and no official source (B3, CVM IPE) records an event: "
                          "Yahoo's adjustment is tier U and unsupported; B3's prices stand unadjusted"))
        .alias("resolution_note"),
    ).drop("_i", "_ls", "_r", "_moved", "_expl", "_small")  # fmt: skip


def level_shifts(j: pl.DataFrame) -> pl.DataFrame:
    """Findings from monthly ratios `r` (Yahoo / ours) per (instrument_id, ticker), sorted by month."""
    g = ["instrument_id", "ticker"]
    lr = pl.col("r").log()
    w = YAHOO_WINDOW
    j = j.with_columns(  # median log-ratio of the w months before and of the w months from this one
        lr.shift(1).rolling_median(w, min_samples=w).over(g).alias("_b"),
        lr.reverse().rolling_median(w, min_samples=w).reverse().over(g).alias("_a"),
        pl.col("month").shift(1).over(g).alias("m0"),
    ).with_columns((pl.col("_a") - pl.col("_b")).alias("_s"), (lr - lr.shift(1)).abs().over(g).alias("_d"))
    # months around a step all show the shift (a plateau of medians): keep, per run of them, the month of the
    # largest one-month jump, i.e. the step itself
    q = pl.col("_s").abs() > math.log(1 + YAHOO_STEP)
    j = j.with_columns(q.alias("_q")).with_columns(
        (pl.col("_q") != pl.col("_q").shift(1)).cum_sum().over(g).alias("_run")
    )
    j = j.filter(pl.col("_q")).filter(pl.col("_d") == pl.col("_d").max().over([*g, "_run"]))
    step = pl.col("_s").exp().round(4)
    return j.select(
        pl.lit("cotahist_vs_yahoo").alias("check_id"),
        pl.lit("warn").alias("severity"),
        pl.lit("instrument").alias("entity_kind"),
        pl.format("{}:{}", "instrument_id", "ticker").alias("entity_id"),
        pl.col("month").alias("vt"),
        step.cast(pl.String).alias("observed"),
        pl.lit("1 (Yahoo and our split-adjusted closes keep one level)").alias("expected"),
        pl.format(
            "{}: Yahoo close / our split-adjusted close shifts level by {} from {} to {}: a split one side applies and "
            "the other does not",
            "ticker",
            step,
            "m0",
            "month",
        ).alias("detail"),
        pl.format("yahoo_chart {} ; price_daily {}@{}", "y_sha", "instrument_id", "trade_date").alias("evidence"),
    )


def mirror_vs_anbima(zones: Zones) -> pl.DataFrame:
    """The pyield mirror (tier S, ADR-0010) against our own ANBIMA files on every date both hold: a bond missing on
    one side, or a PU off by more than 1e-6 BRL or an indicative rate off by more than 1e-4 pp, is a finding."""
    m = read_parquet_dir(zones.staging / "pyield_data" / "bond_rate")
    a = read_parquet_dir(zones.staging / "anbima_titulos_publicos" / "bond_rate")
    if m is None or a is None:
        return _frame([])
    key = ["reference_date", "bond_type", "maturity"]
    m = m.select(*key, pl.col("pu_brl").cast(pl.Float64).alias("pu_m"),
                 pl.col("indicative_rate_pct").cast(pl.Float64).alias("r_m")).unique(key)  # fmt: skip
    a = a.select(
        pl.col("ref_date").alias("reference_date"), "bond_type", pl.col("maturity_date").alias("maturity"),
        pl.col("price_brl").cast(pl.Float64).alias("pu_a"), pl.col("indicative_rate_pct").cast(pl.Float64).alias("r_a"),
    ).unique(key)  # fmt: skip
    both = set(m["reference_date"].unique().to_list()) & set(a["reference_date"].unique().to_list())
    j = m.filter(pl.col("reference_date").is_in(both)).join(
        a.filter(pl.col("reference_date").is_in(both)), on=key, how="full", coalesce=True
    )
    bad = j.filter(
        pl.col("pu_m").is_null() | pl.col("pu_a").is_null()
        | ((pl.col("pu_m") - pl.col("pu_a")).abs() > 1e-6) | ((pl.col("r_m") - pl.col("r_a")).abs() > 1e-4)
    )  # fmt: skip
    return bad.select(
        pl.lit("mirror_vs_anbima").alias("check_id"),
        pl.lit("warn").alias("severity"),
        pl.lit("series").alias("entity_kind"),
        pl.format("{}:{}", "bond_type", "maturity").alias("entity_id"),
        pl.col("reference_date").alias("vt"),
        pl.format("mirror PU {} rate {}", "pu_m", "r_m").alias("observed"),
        pl.format("ANBIMA PU {} rate {}", "pu_a", "r_a").alias("expected"),
        pl.lit("the pyield mirror and ANBIMA's own file disagree on this bond").alias("detail"),
        pl.lit("staging pyield_data/bond_rate; staging anbima_titulos_publicos/bond_rate").alias("evidence"),
    )


def fiagro_duplicate_filing(zones: Zones) -> pl.DataFrame:
    """CVM's FIAGRO monthly file can list one (fund, month, version) twice (22 keys in 2025-26, 15 with different
    figures). Rule: the later delivery (`delivered_on`) is the filing, and on the same day the later line of the
    file; each duplicate is a finding, acknowledged with the line that wins."""
    g = read_parquet_dir(zones.staging / "cvm_fii" / "fiagro_general")
    if g is None:
        return _frame([])
    k = ["cnpj", "reference_date", "version"]
    line = pl.col("raw_locator").str.extract(r"line=(\d+)").cast(pl.Int64)
    d = g.filter(pl.len().over(k) > 1).with_columns(line.alias("_line"))
    d = d.sort([*k, "delivered_on", "_line"]).with_columns(
        pl.col("raw_locator").last().over(k).alias("_winner"), pl.len().over(k).alias("_n")
    )
    w = d.unique(k, keep="last")
    return w.select(
        pl.lit("fiagro_duplicate_filing").alias("check_id"),
        pl.lit("warn").alias("severity"),
        pl.lit("issuer").alias("entity_kind"),
        pl.format("{}:v{}", "cnpj", "version").alias("entity_id"),
        pl.col("reference_date").alias("vt"),
        pl.format("{} rows", "_n").alias("observed"),
        pl.lit("one row per fund, month and version").alias("expected"),
        pl.lit("CVM's FIAGRO monthly file lists this filing more than once").alias("detail"),
        pl.col("_winner").alias("evidence"),
        pl.lit("acknowledged").alias("status"),
        pl.format("rule: the later delivery, then the later file line, is the filing: {}", "_winner").alias(
            "resolution_note"
        ),
    )


CHECKS: dict[str, Callable[[Zones], pl.DataFrame]] = {
    "vna_ntnb_vs_ipca": vna_ntnb_vs_ipca,
    "share_count_unit_mismatch": share_count_unit_mismatch,
    "link_price_jump": link_price_jump,
    "stock_event_unproven": stock_event_unproven,
    "ohlc_inconsistent": ohlc_inconsistent,
    "cotahist_vs_yahoo": cotahist_vs_yahoo,
    "mirror_vs_anbima": mirror_vs_anbima,
    "fiagro_duplicate_filing": fiagro_duplicate_filing,
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
        raw = check(zones)
        ruled = [c for c in ("status", "resolution_note") if c in raw.columns]  # a status a check decides by rule
        df = raw.select(*COLS, *ruled)
        df = df.with_columns(
            pl.struct("check_id", "entity_id", "vt")
            .map_elements(lambda s: finding_id(s["check_id"], s["entity_id"], s["vt"]), return_dtype=pl.String)
            .alias("finding_id")
        )
        if ruled:  # resolutions.toml overrides a rule's decision
            df = df.join(res, on="finding_id", how="left", suffix="_toml").with_columns(
                pl.coalesce("status_toml", "status").fill_null("open").alias("status"),
                pl.coalesce("resolution_note_toml", "resolution_note").alias("resolution_note"),
            )
        else:
            df = df.join(res, on="finding_id", how="left").with_columns(pl.col("status").fill_null("open"))
        good, bad = DQ_FINDING.split(df.select(DQ_FINDING.names).unique("finding_id").sort("finding_id"))
        write_parquet(good, zones.quality / "dq_finding" / f"{name}.parquet")
        out[name] = good.height
        if ingest_run is not None:
            ingest_run.count(f"quality.{name}", in_=df.height, out=good.height, quarantined=bad.height)
    return out
