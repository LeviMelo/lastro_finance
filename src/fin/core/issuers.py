"""Issuers and their instruments (PLAN §4.3.2 `issuer`, §4.4 identity resolution; ADR-0018).

- staging `cvm_cia_cadastro/company`: the CVM register as served (one row per CNPJ, CVM code and market). Contact
  fields of named people (RESP, DRI phones and e-mails, their addresses) are personal data and are not parsed.
- core `issuer`: one row per CNPJ (`issuer_id` = `C` + 12 hex of sha256 of the 14 digits), with its CVM codes, the
  latest register status, sector and names.
- core `issuer_instrument`: which instruments an issuer's shares are. B3's issuer list gives (CVM code → ticker root);
  an instrument belongs to the root when a modern ticker of it (root + 1-2 digits) traded; the link spans the
  instrument's whole trading history (its older tickers included). Method `b3_root`; beyond B3's current list,
  `fca_ticker` (CVM FCA trading codes, 2010-) and `isin_issuer` (the ISIN's issuer code), see `company_links`.
"""

from __future__ import annotations

import hashlib
import io
from collections.abc import Iterable
from typing import Any

import polars as pl

from fin.config import Zones
from fin.ingest.base import Parsed
from fin.schema import Column, Contract
from fin.store.runs import IngestRun
from fin.store.tables import read_parquet_dir, write_parquet

KEEP = {  # register column -> staging column (the rest are contact data, or addresses)
    "CNPJ_CIA": "cnpj",
    "DENOM_SOCIAL": "legal_name",
    "DENOM_COMERC": "trade_name",
    "DT_REG": "registered_on",
    "DT_CONST": "incorporated_on",
    "DT_CANCEL": "cancelled_on",
    "MOTIVO_CANCEL": "cancel_reason",
    "SIT": "status",
    "DT_INI_SIT": "status_since",
    "CD_CVM": "cd_cvm",
    "SETOR_ATIV": "sector",
    "TP_MERC": "market",
    "CATEG_REG": "category",
    "SIT_EMISSOR": "issuer_status",
    "CONTROLE_ACIONARIO": "control",
    "UF": "state",
    "CNPJ_AUDITOR": "auditor_cnpj",
    "AUDITOR": "auditor",
}
DATES = ("registered_on", "incorporated_on", "cancelled_on", "status_since")

COMPANY = Contract(
    table="staging.cvm_cia_cadastro.company",
    version=1,
    description="A row of CVM's register of listed companies (current state as of the file).",
    columns=tuple(
        Column(
            v,
            pl.Date if v in DATES else pl.String,
            f"{k} as written",
            k.lower(),
            "date" if v in DATES else "",
            nullable=v not in ("cnpj", "cd_cvm"),
        )
        for k, v in KEEP.items()
    ),
)
CONTRACTS = {"company": COMPANY}


def parse_register(blob: bytes, row: dict[str, Any]) -> pl.DataFrame:
    text = blob.decode("cp1252")
    head = text.split("\n", 1)[0].rstrip("\r").split(";")
    missing = [c for c in KEEP if c not in head]
    if missing:
        raise ValueError(f"CVM register: columns missing {missing}")
    df = pl.read_csv(io.StringIO(text), separator=";", infer_schema=False, quote_char=None)
    return df.with_row_index("i", offset=2).select(
        *[
            (pl.col(k).str.strptime(pl.Date, "%Y-%m-%d", strict=False) if v in DATES else pl.col(k)).alias(v)
            for k, v in KEEP.items()
        ],
        pl.lit(row["raw_sha256"]).alias("raw_sha256"),
        ("line=" + pl.col("i").cast(pl.String)).alias("raw_locator"),
        pl.lit(row["ingest_run_id"]).alias("ingest_run_id"),
    )


def parse_payload(blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
    if str(row["dataset_id"]) == "cad_cia_aberta":
        yield Parsed("company", "all", parse_register(blob, row))


ISSUER = Contract(
    table="core.issuer",
    version=1,
    description="A company identified by its CNPJ (our surrogate id), with its CVM codes and register state.",
    provenance=False,
    columns=(
        Column("issuer_id", pl.String, "C + 12 hex of sha256(CNPJ digits)", "id do emissor", nullable=False),
        Column("cnpj", pl.String, "14 digits", "CNPJ", nullable=False),
        Column(
            "cd_cvm", pl.String, "CVM codes, comma-separated, newest registration first", "códigos CVM", nullable=False
        ),
        Column("legal_name", pl.String, "DENOM_SOCIAL (current)", "razão social"),
        Column("trade_name", pl.String, "DENOM_COMERC (current)", "nome comercial"),
        Column("status", pl.String, "SIT of the newest registration", "situação"),
        Column("sector", pl.String, "SETOR_ATIV", "setor"),
        Column("category", pl.String, "CATEG_REG", "categoria"),
        Column("registered_on", pl.Date, "first DT_REG", "registro", "date"),
        Column("cancelled_on", pl.Date, "DT_CANCEL of the newest registration", "cancelamento", "date"),
    ),
    key=("issuer_id",),
)

LINK = Contract(
    table="core.issuer_instrument",
    version=1,
    description="An instrument issued by an issuer, over the dates its ticker traded.",
    provenance=False,
    columns=(
        Column("issuer_id", pl.String, "issuer", "id do emissor", nullable=False),
        Column("instrument_id", pl.String, "instrument", "id do instrumento", nullable=False),
        Column("root", pl.String, "B3 ticker root", "raiz", nullable=False),
        Column(
            "vt_from",
            pl.Date,
            "first session of a ticker of this root on this instrument",
            "de",
            "date",
            nullable=False,
        ),
        Column("vt_to", pl.Date, "last such session", "até", "date", nullable=False),
        Column(
            "method",
            pl.String,
            "b3_root, fca_ticker, isin_issuer (company) or fund_isin (FII quota)",
            "método",
            nullable=False,
        ),
    ),
    key=("issuer_id", "instrument_id", "root"),
)


def issuer_id(cnpj_digits: str) -> str:
    return "C" + hashlib.sha256(cnpj_digits.encode()).hexdigest()[:12]


ISIN_MIN_REPORTS = 3  # an owner needs at least this many reports and a strict majority of the ISIN's reports


def isin_owners(pairs: pl.DataFrame) -> pl.DataFrame:
    """(isin, cnpj, reports, share) of each quota ISIN's owner: the CNPJ with a strict majority of the reports that
    name the ISIN (CVM monthly reports plus Fundos.NET notices). Some funds write another fund's ISIN in a report
    (BBPO11: 204 reports by its fund, 5 and 4 by two others, 2019): those claims never make a link (`fund_isin_claim`
    findings). An ISIN with no majority has no owner."""
    n = pairs.group_by("isin", "cnpj").agg(pl.len().alias("reports"))
    return (
        n.with_columns((pl.col("reports") / pl.col("reports").sum().over("isin")).alias("share"))
        .filter((pl.col("share") > 0.5) & (pl.col("reports") >= ISIN_MIN_REPORTS))
        .select("isin", "cnpj", "reports", "share")
    )


def fund_isin_pairs(zones: Zones) -> pl.DataFrame | None:
    """(cnpj, isin, fund_name, segment) of every report naming a quota ISIN: CVM FII monthly reports and Fundos.NET
    payout notices."""
    pairs: list[pl.DataFrame] = []
    g = read_parquet_dir(zones.staging / "cvm_fii" / "monthly_general")
    if g is not None:
        pairs.append(
            g.sort("reference_date").select(
                pl.col("cnpj").str.replace_all(r"\D", "").alias("cnpj"), "isin", "fund_name", "segment"
            )
        )
    d = read_parquet_dir(zones.staging / "b3_fundosnet" / "distribution")
    if d is not None:
        pairs.append(
            d.select(
                pl.col("fund_cnpj").str.replace_all(r"\D", "").alias("cnpj"),
                "isin",
                "fund_name",
                pl.lit(None, dtype=pl.String).alias("segment"),
            )
        )
    if not pairs:
        return None
    # a fund quota's ISIN has CTF at letters 7-9; some FII reports name a share they hold (MBRF3's ISIN, 2026)
    return (
        pl.concat(pairs)
        .filter((pl.col("isin").str.len_chars() == 12) & (pl.col("isin").str.slice(6, 3) == "CTF"))
        .drop_nulls(["cnpj", "isin"])
    )


def fund_issuers(zones: Zones) -> tuple[pl.DataFrame, pl.DataFrame] | None:
    """(issuer rows, issuer_instrument rows) for funds whose quotas trade: (CNPJ, quota ISIN) pairs from CVM's FII
    monthly reports (`cvm_fii` monthly_general) and Fundos.NET payout notices, joined to instruments by ISIN
    (method `fund_isin`, the root being the first four letters of the quota's ticker)."""
    p = fund_isin_pairs(zones)
    ids_path = zones.core / "instrument_identifier" / "instrument_identifier.parquet"
    if p is None or not ids_path.exists():
        return None
    owners = isin_owners(p)
    issuers = (
        p.group_by("cnpj")
        .agg(pl.col("fund_name").drop_nulls().last(), pl.col("segment").drop_nulls().last())
        .select(
            pl.col("cnpj").map_elements(issuer_id, return_dtype=pl.String).alias("issuer_id"),
            "cnpj",
            pl.lit("").alias("cd_cvm"),
            pl.col("fund_name").alias("legal_name"),
            pl.col("fund_name").alias("trade_name"),
            pl.lit(None, dtype=pl.String).alias("status"),
            pl.col("segment").alias("sector"),
            pl.lit("Fundo (FII/Fiagro)").alias("category"),
            pl.lit(None, dtype=pl.Date).alias("registered_on"),
            pl.lit(None, dtype=pl.Date).alias("cancelled_on"),
        )
        .select(ISSUER.names)
    )
    ids = pl.read_parquet(ids_path)
    isin = ids.filter(pl.col("scheme") == "ISIN").select("instrument_id", pl.col("value").alias("isin"))
    tick = (
        ids.filter(pl.col("scheme") == "TICKER")
        .group_by("instrument_id")
        .agg(pl.col("value").sort().last().str.slice(0, 4).alias("root"))
    )
    span = pl.read_parquet(zones.core / "instrument" / "instrument.parquet").select(
        "instrument_id", pl.col("first_trade").alias("vt_from"), pl.col("last_trade").alias("vt_to")
    )
    link = (
        owners.select("cnpj", "isin")
        .join(isin, on="isin")
        .join(tick, on="instrument_id", how="left")
        .join(span, on="instrument_id")
        .select(
            pl.col("cnpj").map_elements(issuer_id, return_dtype=pl.String).alias("issuer_id"),
            "instrument_id",
            pl.col("root").fill_null(""),
            "vt_from",
            "vt_to",
            pl.lit("fund_isin").alias("method"),
        )
    )
    return issuers, link


FCA_WINDOW = "1y"  # an FCA trading code names the ticker valid within a year of the form's reference date


def company_links(zones: Zones, known: pl.DataFrame, span: pl.DataFrame, issuers: pl.DataFrame) -> pl.DataFrame:
    """Links beyond B3's current issuer list (OQ-7), for instruments it does not reach:
    - `fca_ticker`: CVM FCA securities (2010-) give (CNPJ, trading code) per form; the code joins the ticker valid
      within `FCA_WINDOW` of the form's date (tickers are reused: the date matters).
    - `isin_issuer`: B3's issuer code, letters 3-6 of the ISIN (BR**PETR**ACNPR6), stays with the company across
      ticker changes; an instrument with no link takes the issuer of a linked share or unit whose ISIN has its code,
      when that code maps to exactly one issuer (fund quotas, CTF, excluded) and the instrument traded on or after
      the issuer's CVM registration (Embraer's 1991-2002 classes share EMBR with the CNPJ registered in 2006)."""
    ids = pl.read_parquet(zones.core / "instrument_identifier" / "instrument_identifier.parquet")
    tick = ids.filter(pl.col("scheme") == "TICKER").select("instrument_id", "value", "vt_from", "vt_to")
    isin = ids.filter(pl.col("scheme") == "ISIN").select("instrument_id", pl.col("value").alias("isin"))
    out: list[pl.DataFrame] = []
    fca = read_parquet_dir(zones.staging / "cvm_fca" / "security")
    if fca is not None:
        f = (
            fca.select(
                pl.col("cnpj").str.replace_all(r"\D", "").alias("cnpj"),
                pl.col("trading_code").str.strip_chars().str.to_uppercase().alias("value"),
                "reference_date",
            )
            .filter(pl.col("value").str.contains(r"^[A-Z0-9]{4}\d{1,2}$"))
            .unique()
            .join(tick, on="value")
            .filter(
                (pl.col("vt_from") <= pl.col("reference_date").dt.offset_by(FCA_WINDOW))
                & (pl.col("vt_to") >= pl.col("reference_date").dt.offset_by("-" + FCA_WINDOW))
            )
        )
        one = f.group_by("instrument_id").agg(pl.col("cnpj").n_unique().alias("k")).filter(pl.col("k") == 1)
        out.append(
            f.join(one, on="instrument_id")
            .group_by("cnpj", "instrument_id")
            .agg(pl.col("value").sort().last().str.slice(0, 4).alias("root"))
            .join(span, on="instrument_id")
            .select(
                pl.col("cnpj").map_elements(issuer_id, return_dtype=pl.String).alias("issuer_id"),
                "instrument_id",
                "root",
                "vt_from",
                "vt_to",
                pl.lit("fca_ticker").alias("method"),
            )
        )
    linked = pl.concat([known.select("issuer_id", "instrument_id"), *[o.select("issuer_id", "instrument_id")
                                                                     for o in out]]).unique()  # fmt: skip
    code = (
        linked.join(isin, on="instrument_id")
        .filter(~pl.col("isin").str.slice(6, 3).is_in(["CTF"]))
        .with_columns(pl.col("isin").str.slice(2, 4).alias("code"))
        .group_by("code")
        .agg(pl.col("issuer_id").n_unique().alias("k"), pl.col("issuer_id").first())
        .filter(pl.col("k") == 1)
    )
    ext = (
        isin.filter(~pl.col("instrument_id").is_in(linked["instrument_id"].implode()))
        .filter(pl.col("isin").str.slice(6, 3) != "CTF")
        .with_columns(pl.col("isin").str.slice(2, 4).alias("code"))
        .join(code.select("code", "issuer_id"), on="code")
        .join(
            tick.group_by("instrument_id").agg(pl.col("value").sort().last().str.slice(0, 4).alias("root")),
            on="instrument_id",
            how="left",
        )
        .join(span, on="instrument_id")
        .join(issuers.select("issuer_id", "registered_on"), on="issuer_id", how="left")
        .filter(pl.col("registered_on").is_null() | (pl.col("vt_to") >= pl.col("registered_on")))
        .select(
            "issuer_id",
            "instrument_id",
            pl.col("root").fill_null(pl.col("code")),
            "vt_from",
            "vt_to",
            pl.lit("isin_issuer").alias("method"),
        )
    )
    return pl.concat([*out, ext], how="vertical_relaxed").select(LINK.names)


def build(zones: Zones, run: IngestRun | None = None) -> dict[str, int]:
    reg = read_parquet_dir(zones.staging / "cvm_cia_cadastro" / "company")
    if reg is None or not reg.height:
        return {}
    reg = reg.with_columns(pl.col("cnpj").str.replace_all(r"\D", "").alias("cnpj"))
    reg = reg.sort("cnpj", pl.col("registered_on").fill_null(pl.date(1900, 1, 1)), descending=[False, True])
    issuers = (
        reg.group_by("cnpj", maintain_order=True)
        .agg(
            pl.col("cd_cvm").unique(maintain_order=True).str.join(",").alias("cd_cvm"),
            pl.col("legal_name").first(),
            pl.col("trade_name").first(),
            pl.col("status").first(),
            pl.col("sector").first(),
            pl.col("category").first(),
            pl.col("registered_on").min(),
            pl.col("cancelled_on").first(),
        )
        .with_columns(pl.col("cnpj").map_elements(issuer_id, return_dtype=pl.String).alias("issuer_id"))
        .select(ISSUER.names)
    )
    funds = fund_issuers(zones)
    if funds is not None:  # FII/Fiagro funds: CVM's monthly reports and Fundos.NET give CNPJ and quota ISIN
        issuers = pl.concat([issuers, funds[0].filter(~pl.col("cnpj").is_in(issuers["cnpj"].to_list()))])
    out: dict[str, int] = {}
    good, bad = ISSUER.split(issuers)
    write_parquet(good, zones.core / "issuer" / "issuer.parquet")
    out["issuer"], out["issuer:quarantined"] = good.height, bad.height

    b3 = read_parquet_dir(zones.staging / "b3_company_events" / "issuer")
    ids_path = zones.core / "instrument_identifier" / "instrument_identifier.parquet"
    if b3 is not None and ids_path.exists():
        code_root = b3.select(pl.col("code_cvm").cast(pl.Int64).alias("cd"), "root").unique()
        cvm = reg.select(pl.col("cd_cvm").cast(pl.Int64, strict=False).alias("cd"), "cnpj").drop_nulls().unique()
        roots = code_root.join(cvm, on="cd").select("cnpj", "root").unique()
        tick = pl.read_parquet(ids_path).filter(
            (pl.col("scheme") == "TICKER") & pl.col("value").str.contains(r"^[A-Z0-9]{4}\d{1,2}$")
        )
        tick = tick.with_columns(pl.col("value").str.slice(0, 4).alias("root"))
        span = pl.read_parquet(zones.core / "instrument" / "instrument.parquet").select(
            "instrument_id", pl.col("first_trade").alias("vt_from"), pl.col("last_trade").alias("vt_to")
        )
        isin_of = pl.read_parquet(ids_path).filter(pl.col("scheme") == "ISIN")
        quota = isin_of.filter(pl.col("value").str.slice(6, 3) == "CTF")["instrument_id"].implode()
        link = (  # a company's root never covers a fund quota (MBRF11, an FII 2011-22; Marfrig took MBRF in 2025)
            tick.filter(~pl.col("instrument_id").is_in(quota))
            .join(roots, on="root")
            .select("cnpj", "instrument_id", "root")
            .unique()
            .join(span, on="instrument_id")
            .with_columns(
                pl.col("cnpj").map_elements(issuer_id, return_dtype=pl.String).alias("issuer_id"),
                pl.lit("b3_root").alias("method"),
            )
            .select(LINK.names)
        )
        link = pl.concat([link, company_links(zones, link, span, issuers)], how="vertical_relaxed")
        if funds is not None:
            link = pl.concat([link, funds[1]], how="vertical_relaxed").unique(["issuer_id", "instrument_id", "root"])
        good, bad = LINK.split(link)
        write_parquet(good.sort("issuer_id", "vt_from"), zones.core / "issuer_instrument" / "issuer_instrument.parquet")
        out["issuer_instrument"], out["issuer_instrument:quarantined"] = good.height, bad.height
    if run is not None:
        run.count("core.issuer", in_=issuers.height, out=out["issuer"])
    return out
