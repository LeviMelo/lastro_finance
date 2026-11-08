"""Debentures as instruments of their own (PLAN §4.3.2; ADR-0028).

Core `debenture`: one row per SND code, built from staging `snd_debentures/caracteristicas` (the terms register, dead
debentures included). Debentures are **not** rows of `instrument`: that table is COTAHIST's exchange-traded universe
with an ISIN as identity, and a debenture's ISIN is not an identity (42 valid ISINs are shared by several series, 200
terms rows have none, 18 are placeholders). The key is SND's code, which is unique per debenture in the register.

- `debenture_id` = `D` + 12 hex of sha256(`SND:` + code).
- `isin` is kept only when it is a well-formed ISIN with a valid check digit; `isin_shared_by` counts the codes that
  carry it. Time-ranged ISIN and code history is not available: SND serves a current snapshot, so changes show up as
  versions in staging (ADR-0014) and in `kt_first_seen_at` here.
- `issuer_cnpj` is the 14 digits of the register row with the lowest CNPJ; a debenture co-issued by two companies
  has one row per issuer in the register, the others go to `co_issuer_cnpjs`. `issuer_id` is set when that CNPJ is in
  core `issuer`.
- The latest version of the terms of each (code, issuer) wins (by the first fetch that carried it); dead debentures
  keep their last terms. Two register rows have a maturity before the issue date (CPCM12, PLIM15, 2026-11-08): kept
  as published, not dropped.

Daily PU (`snd_pu_historico`) and trades (`b3_fixed_income`, `snd_debentures/secondary_price`) join on the code; the
build reports how many debentures have each.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import polars as pl

from fin.config import Zones
from fin.schema import Column, Contract, Rule
from fin.store.manifest import Manifest
from fin.store.runs import IngestRun
from fin.store.tables import write_parquet

DEC = pl.Decimal(38, 12)
ISIN_FORM = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")

DEBENTURE = Contract(
    table="core.debenture",
    version=1,
    description="A debenture registered in SND (terms as of the latest version seen), identified by our surrogate id.",
    columns=(
        Column("debenture_id", pl.String, "surrogate id: D + 12 hex of sha256('SND:' + ticker)", "id", "", False),
        Column("ticker", pl.String, "SND/B3 code of the debenture", "código do ativo", "", False),
        Column("isin", pl.String, "ISIN when well formed with a valid check digit, else null", "ISIN"),
        Column(
            "isin_shared_by", pl.Int32, "number of codes carrying that ISIN (1 = unique)", "códigos com o ISIN", "count"
        ),
        Column("issuer_name", pl.String, "issuer as SND writes it", "emissor"),
        Column(
            "issuer_cnpj",
            pl.String,
            "issuer CNPJ, 14 digits (lowest CNPJ among the register rows of the code)",
            "CNPJ do emissor",
        ),
        Column("co_issuer_cnpjs", pl.List(pl.String), "CNPJs of further issuers of the same code", "co-emissores"),
        Column("issuer_id", pl.String, "core issuer id when the CNPJ is in core issuer, else null", "id do emissor"),
        Column("series", pl.String, "series (UNI = single)", "série"),
        Column("issue_number", pl.String, "issue number within the issuer", "emissão"),
        Column("issue_date", pl.Date, "issue date", "data de emissão", "date", False),
        Column("maturity_date", pl.Date, "original maturity; null when SND has none", "vencimento", "date"),
        Column("situation", pl.String, "Registrado or Excluído at the latest snapshot", "situação"),
        Column("exit_date", pl.Date, "exit date when Excluído (else null)", "data de saída", "date"),
        Column("exit_reason", pl.String, "'dd/mm/yyyy - REASON' as written", "motivo de saída"),
        Column("indexer", pl.String, "index: DI, IPCA, IGP-M, TR, PRÉ, SEM-ÍNDICE...", "indexador"),
        Column("index_percent", DEC, "percent of the index (100 = 100% of DI)", "% do indexador", "% of index"),
        Column(
            "coupon_rate", DEC, "spread/coupon rate over the index (SND 'Juros Critério Novo - Taxa')", "taxa", "% a.a."
        ),
        Column("incentivised", pl.Boolean, "Lei 12.431 incentivised debenture", "incentivada (Lei 12.431)"),
        Column("currency", pl.String, "currency of the nominal value at issue", "moeda"),
        Column("nominal_at_issue", DEC, "nominal value at issue", "valor nominal na emissão", "currency per debenture"),
        Column("qty_issued", pl.Int64, "debentures issued", "quantidade emitida", "debentures"),
        Column(
            "kt_first_seen_at",
            pl.Datetime("us", "UTC"),
            "first fetch that carried these terms",
            "visto em",
            "timestamp",
        ),
    ),
    rules=(Rule("cnpj_14_digits", pl.col("issuer_cnpj").is_null() | pl.col("issuer_cnpj").str.contains(r"^\d{14}$")),),
    key=("debenture_id",),
)


def debenture_id(ticker: str) -> str:
    return "D" + hashlib.sha256(f"SND:{ticker}".encode()).hexdigest()[:12]


def isin_valid(isin: str | None) -> bool:
    """Well-formed ISIN with a valid Luhn check digit (ISO 6166)."""
    if not isin or not ISIN_FORM.match(isin):
        return False
    digits = "".join(str(int(ch, 36)) for ch in isin)
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            n = n // 10 + n % 10
        total += n
    return total % 10 == 0


def _tickers(directory: Path, column: str = "ticker") -> set[str]:
    if not directory.exists() or not any(directory.rglob("*.parquet")):
        return set()
    glob = str(directory / "**" / "*.parquet")
    return set(pl.scan_parquet(glob, hive_partitioning=False).select(column).unique().collect()[column].to_list())


def terms(zones: Zones) -> pl.DataFrame | None:
    """The latest version of every (code, issuer) row of the register, with the first fetch that carried it."""
    d = zones.staging / "snd_debentures" / "caracteristicas"
    if not d.exists() or not any(d.rglob("*.parquet")):
        return None
    s = pl.read_parquet(str(d / "**" / "*.parquet"), hive_partitioning=False)
    seen = (
        Manifest(zones.manifest)
        .read()
        .filter(pl.col("source_id") == "snd_debentures")
        .group_by("raw_sha256")
        .agg(pl.col("fetched_at").min().alias("kt_first_seen_at"))
    )
    s = s.join(seen, on="raw_sha256", how="left").sort("ticker", "issuer_cnpj", "kt_first_seen_at")
    return s.group_by("ticker", "issuer_cnpj", maintain_order=True).last()


def build(zones: Zones, run: IngestRun | None = None) -> dict[str, int]:
    t = terms(zones)
    if t is None or not t.height:
        return {}
    # one row per code: the issuer with the lowest CNPJ; the register's other issuers of that code are co-issuers
    t = t.sort("ticker", "issuer_cnpj")
    first = t.unique("ticker", keep="first", maintain_order=True)
    co = (
        t.join(first.select("ticker", pl.col("issuer_cnpj").alias("_main")), on="ticker")
        .filter(pl.col("issuer_cnpj").ne_missing(pl.col("_main")) & pl.col("issuer_cnpj").is_not_null())
        .group_by("ticker")
        .agg(pl.col("issuer_cnpj").unique().sort().alias("co_issuer_cnpjs"))
    )
    first = first.join(co, on="ticker", how="left").with_columns(
        pl.col("co_issuer_cnpjs").fill_null(pl.lit([], dtype=pl.List(pl.String)))
    )
    clean = first.with_columns(
        pl.when(pl.col("isin").map_elements(isin_valid, return_dtype=pl.Boolean)).then(pl.col("isin")).alias("isin")
    )
    shared = (
        clean.filter(pl.col("isin").is_not_null()).group_by("isin").agg(pl.len().cast(pl.Int32).alias("isin_shared_by"))
    )
    issuers_path = zones.core / "issuer" / "issuer.parquet"
    issuers = (
        pl.read_parquet(issuers_path).select("issuer_id", pl.col("cnpj").alias("issuer_cnpj"))
        if issuers_path.exists()
        else pl.DataFrame(schema={"issuer_id": pl.String, "issuer_cnpj": pl.String})
    )
    frame = (
        clean.join(shared, on="isin", how="left")
        .join(issuers, on="issuer_cnpj", how="left")
        .with_columns(
            pl.col("ticker").map_elements(debenture_id, return_dtype=pl.String).alias("debenture_id"),
            pl.when(pl.col("situation").str.starts_with("Exclu"))
            .then(pl.col("exit_or_new_maturity_date"))
            .alias("exit_date"),
            (pl.col("incentivised") == "S").alias("incentivised"),
            pl.col("issue_currency").alias("currency"),
            pl.col("nominal_at_issue"),
        )
        .select(DEBENTURE.names)
        .sort("ticker")
    )
    good, bad = DEBENTURE.split(frame)
    write_parquet(good, zones.core / "debenture" / "debenture.parquet")
    q = zones.quarantine / "core" / "debenture.parquet"
    if bad.height:
        write_parquet(bad, q)
    else:
        q.unlink(missing_ok=True)

    codes = set(good["ticker"].to_list())
    pu = _tickers(zones.staging / "snd_pu_historico" / "debenture_pu")
    b3 = _tickers(zones.staging / "b3_fixed_income" / "fi_trade")
    sec = _tickers(zones.staging / "snd_debentures" / "secondary_price")
    out = {
        "debenture": good.height,
        "debenture:quarantined": bad.height,
        "with_issuer_id": int(good["issuer_id"].is_not_null().sum()),
        "co_issued": int((good["co_issuer_cnpjs"].list.len() > 0).sum()),
        "with_valid_isin": int(good["isin"].is_not_null().sum()),
        "with_pu_history": len(codes & pu),
        "with_snd_secondary_trades": len(codes & sec),
        "with_b3_otc_trades": len(codes & b3),
        "pu_tickers_not_in_register": len(pu - codes),
    }
    if run is not None:
        run.count("core.debenture", in_=frame.height, out=good.height, quarantined=bad.height)
    return out
