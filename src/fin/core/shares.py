"""Shares outstanding per filing, in units (ADR-0020).

CVM's `composicao_capital` states no unit, and companies use both: measured 2026-11-07 against B3's current share
counts (Supplement `totalNumberShares`) on 340 issuers, 201 file in units (PETR 12,888,732,761 = B3), 93 in thousands
(ITUB 11,026,869 vs 11,026,869,192), and some switch over time (Bradesco: thousands in DFP 2022, units in 2026).

Inference, per issuer and form, filings in date order:
1. the latest filing is anchored to B3's current count: unit 1 if count × 1 is within 30 % of B3's, 1,000 if count ×
   1,000 is, else unknown;
2. walking back, a filing keeps the unit of the next one unless the raw counts differ by a factor near 1,000 (between
   300 and 3,000, or its inverse), which toggles it.
Filings of issuers without a B3 count, or whose anchor is unknown, get `unit` null and no unit-free count.
"""

from __future__ import annotations

import polars as pl

from fin.config import Zones
from fin.schema import Column, Contract
from fin.store.runs import IngestRun
from fin.store.tables import read_parquet_dir, write_parquet

SHARE_COUNT = Contract(
    table="core.share_count",
    version=2,
    description="Shares paid in and in treasury per filing, converted to units by the inferred filing unit.",
    provenance=False,
    columns=(
        Column("issuer_cnpj", pl.String, "14 digits", "CNPJ", nullable=False),
        Column("form", pl.String, "dfp or itr", "formulário", nullable=False),
        Column("reference_date", pl.Date, "period of the filing", "data de referência", "date", nullable=False),
        Column("version", pl.Int16, "filing version", "versão", "count", nullable=False),
        Column(
            "received_on", pl.Date, "CVM delivery date of the version (knowledge date)", "data de recebimento", "date"
        ),
        Column("unit", pl.Int32, "inferred: 1 (units) or 1000 (thousands); null when unknown", "unidade", "shares"),
        Column("common", pl.Int64, "common shares paid in, units", "ações ordinárias", "shares"),
        Column("preferred", pl.Int64, "preferred shares paid in, units", "ações preferenciais", "shares"),
        Column("total", pl.Int64, "total shares paid in, units", "total de ações", "shares"),
        Column("treasury", pl.Int64, "total shares in treasury, units", "ações em tesouraria", "shares"),
        Column("common_treasury", pl.Int64, "common shares in treasury, units", "ON em tesouraria", "shares"),
        Column("preferred_treasury", pl.Int64, "preferred shares in treasury, units", "PN em tesouraria", "shares"),
        Column(
            "total_as_filed",
            pl.Int64,
            "total as written in the filing",
            "total como arquivado",
            "filing unit",
            nullable=False,
        ),
        Column("anchor_b3_total", pl.Int64, "B3's current total (anchor of the latest filing)", "total B3", "shares"),
    ),
    key=("issuer_cnpj", "form", "reference_date", "version"),
)


def infer_units(counts: list[int], anchor: int | None) -> list[int | None]:
    """Units for filings in date order (oldest first), the last anchored to `anchor`."""
    n = len(counts)
    out: list[int | None] = [None] * n
    if not n or anchor is None or counts[-1] <= 0:
        return out
    for u in (1, 1000):
        if abs(counts[-1] * u / anchor - 1) <= 0.3:
            out[-1] = u
    if out[-1] is None:
        return out
    for i in range(n - 2, -1, -1):
        nxt, cur = counts[i + 1], counts[i]
        unit = out[i + 1]
        if cur > 0 and nxt > 0 and unit is not None:
            r = nxt / cur
            if 300 <= r <= 3000:  # the later filing is in units, this one in thousands
                unit = 1000 if unit == 1 else unit
            elif 1 / 3000 <= r <= 1 / 300:
                unit = 1 if unit == 1000 else unit
        out[i] = unit
    return out


def b3_counts(zones: Zones) -> pl.DataFrame:
    """B3's current total shares per CVM code, from the latest archived Supplement of each issuer."""
    import json

    from fin.store.manifest import Manifest
    from fin.store.raw import RawStore

    m = (
        Manifest(zones.manifest)
        .read()
        .filter(
            (pl.col("source_id") == "b3_company_events")
            & (pl.col("dataset_id") == "supplement")
            & (pl.col("http_status") == 200)
        )
        .sort("fetched_at")
        .unique("notes", keep="last")
    )
    raw = RawStore(zones.raw)
    rows: list[tuple[int, int]] = []
    for sha in m["raw_sha256"].to_list():
        doc = json.loads(raw.read(sha))
        if doc and doc[0].get("totalNumberShares") and doc[0].get("codeCVM"):
            rows.append((int(doc[0]["codeCVM"]), int(str(doc[0]["totalNumberShares"]).replace(".", ""))))
    return pl.DataFrame(rows, schema={"cd": pl.Int64, "anchor_b3_total": pl.Int64}, orient="row").unique("cd")


def build(zones: Zones, run: IngestRun | None = None) -> dict[str, int]:
    sc = read_parquet_dir(zones.staging / "cvm_dfp_itr" / "share_capital")
    reg = read_parquet_dir(zones.staging / "cvm_cia_cadastro" / "company")
    if sc is None or reg is None:
        return {}
    sc = sc.with_columns(pl.col("cnpj").str.replace_all(r"\D", "").alias("issuer_cnpj")).unique(
        ["issuer_cnpj", "form", "reference_date", "version"], keep="last"
    )
    cd = reg.select(
        pl.col("cnpj").str.replace_all(r"\D", "").alias("issuer_cnpj"), pl.col("cd_cvm").cast(pl.Int64, strict=False)
    ).drop_nulls()
    anchor = (
        cd.join(b3_counts(zones), left_on="cd_cvm", right_on="cd")
        .group_by("issuer_cnpj")
        .agg(pl.col("anchor_b3_total").first())
    )
    docs = read_parquet_dir(zones.staging / "cvm_dfp_itr" / "document")
    if docs is not None:
        recv = docs.group_by("form", "cnpj", "reference_date", "version").agg(pl.col("received_on").min())
        sc = sc.join(recv, on=["form", "cnpj", "reference_date", "version"], how="left")
    else:
        sc = sc.with_columns(pl.lit(None, dtype=pl.Date).alias("received_on"))
    sc = sc.join(anchor, on="issuer_cnpj", how="left").sort("issuer_cnpj", "form", "reference_date", "version")
    parts: list[pl.DataFrame] = []
    for _, g in sc.group_by("issuer_cnpj", "form", maintain_order=True):
        units = infer_units(g["total_paid_in"].fill_null(0).to_list(), g["anchor_b3_total"][0])
        parts.append(g.with_columns(pl.Series("unit", units, dtype=pl.Int32)))
    df = pl.concat(parts)
    u = pl.col("unit").cast(pl.Int64)
    out = df.select(
        "issuer_cnpj",
        "form",
        "reference_date",
        "version",
        "received_on",
        "unit",
        (pl.col("common_paid_in") * u).alias("common"),
        (pl.col("preferred_paid_in") * u).alias("preferred"),
        (pl.col("total_paid_in") * u).alias("total"),
        (pl.col("total_treasury") * u).alias("treasury"),
        (pl.col("common_treasury") * u).alias("common_treasury"),
        (pl.col("preferred_treasury") * u).alias("preferred_treasury"),
        pl.col("total_paid_in").fill_null(0).alias("total_as_filed"),
        "anchor_b3_total",
    )
    good, bad = SHARE_COUNT.split(out)
    write_parquet(good, zones.core / "share_count" / "share_count.parquet")
    res = {"share_count": good.height, "with_unit": int(good["unit"].is_not_null().sum())}
    if run is not None:
        run.count("core.share_count", in_=out.height, out=good.height, quarantined=bad.height)
    return res
