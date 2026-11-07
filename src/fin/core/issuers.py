"""Issuers and their instruments (PLAN §4.3.2 `issuer`, §4.4 identity resolution; ADR-0018).

- staging `cvm_cia_cadastro/company`: the CVM register as served (one row per CNPJ, CVM code and market). Contact
  fields of named people (RESP, DRI phones and e-mails, their addresses) are personal data and are not parsed.
- core `issuer`: one row per CNPJ (`issuer_id` = `C` + 12 hex of sha256 of the 14 digits), with its CVM codes, the
  latest register status, sector and names.
- core `issuer_instrument`: which instruments an issuer's shares are. B3's issuer list gives (CVM code → ticker root);
  an instrument belongs to the root when a modern ticker of it (root + 1-2 digits) traded; the link spans the
  instrument's whole trading history (its older tickers included). Method `b3_root`.
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
        Column("method", pl.String, "b3_root", "método", nullable=False),
    ),
    key=("issuer_id", "instrument_id", "root"),
)


def issuer_id(cnpj_digits: str) -> str:
    return "C" + hashlib.sha256(cnpj_digits.encode()).hexdigest()[:12]


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
        link = (
            tick.join(roots, on="root")
            .select("cnpj", "instrument_id", "root")
            .unique()
            .join(span, on="instrument_id")
            .with_columns(
                pl.col("cnpj").map_elements(issuer_id, return_dtype=pl.String).alias("issuer_id"),
                pl.lit("b3_root").alias("method"),
            )
            .select(LINK.names)
        )
        good, bad = LINK.split(link)
        write_parquet(good.sort("issuer_id", "vt_from"), zones.core / "issuer_instrument" / "issuer_instrument.parquet")
        out["issuer_instrument"], out["issuer_instrument:quarantined"] = good.height, bad.height
    if run is not None:
        run.count("core.issuer", in_=issuers.height, out=out["issuer"])
    return out
