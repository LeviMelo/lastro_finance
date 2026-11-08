"""B3 Fundos.NET 'Composição da Carteira (CDA)' of ETFs -> staging `position`, `net_assets`, `listing`
(docs/sources/b3_fundosnet_cda.md).

One XML per fund and month (category 6, type 63): what the fund holds at month end, the ETF counterpart of CVM's
CDA open data, which has no ETF rows. Measured 2026-11-08 on 164 documents spread over 2018-09 → 2026-11:
- layout `cda` (142): root `DOC_ARQ`, namespace `urn:cda`, VERSAO 3.0; one `INFORM` per fund with `CNPJ_FDO`,
  `VL_PL` and `LISTA_ATIV`, whose children are asset blocks (`TIT_PUB`, `COTAS`, `DEMAIS_CODIF`, `DEMAIS_N_CODIF`,
  `INV_EXT`, `DEP_PRAZO_TIT_IF`, `TIT_AGRO_CRED_PRIV`), each holding one `APLIC` (negotiated and final position);
  values with a decimal comma;
- layout `legacy` (19, 2018-09 → 2023-07): root `DadosEconomicoFinanceiros`, no namespace, a flat list of
  `Aplicacao` with the asset described in text; values with a decimal point;
- a third root, `DOC_ARQ` without namespace and with `APLIC_ATIVO`, is a FIDC's portfolio (1 of 164): not an ETF's
  CDA, counted as not data. A body that is not XML ("Ocorreu um enviar o arquivo XML.", 32 bytes) is not data too.
- some documents declare Windows-1252 and hold UTF-8 (1240750): a body that decodes as UTF-8 is read as UTF-8.
An element or block outside the surveyed ones raises `LayoutError`. The issuer of a position held by a natural
person (11-digit tax id or `TP_PF_PJ_EMIS` PF) is not kept: neither the CPF nor the name.
A CNPJ of 12-13 digits (leading zeros lost in the source) is padded to 14.
Codes (`COD_TP_ATIV`, `COD_TP_APLIC`) are kept as written; no code table was verified.
"""

from __future__ import annotations

import dataclasses
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from typing import Any

import polars as pl

from fin.ingest import fundosnet
from fin.ingest.base import NotData, Parsed
from fin.schema import Column, Contract, Rule

MONEY = pl.Decimal(38, 4)
QTY = pl.Decimal(38, 6)
RATE = pl.Decimal(38, 6)
BOM = b"\xef\xbb\xbf"


class LayoutError(ValueError):
    pass


POSITION = Contract(
    table="staging.b3_fundosnet_cda.position",
    version=1,
    description="An ETF's portfolio at month end, one row per asset line, as delivered to Fundos.NET.",
    columns=(
        Column("doc_id", pl.Int64, "Fundos.NET document id", "id do documento", nullable=False),
        Column("fund_cnpj", pl.String, "CNPJ_FDO of the INFORM / CNPJFundo, 14 digits", "CNPJ", nullable=False),
        Column(
            "reference_month",
            pl.Date,
            "DT_COMPT MM/YYYY as the first day of the month",
            "competência",
            "date",
            nullable=False,
        ),
        Column(
            "line",
            pl.Int32,
            "ordinal of the asset line in the document",
            "linha do documento",
            "ordinal",
            nullable=False,
        ),
        Column(
            "layout", pl.String, "cda (urn:cda v3.0) or legacy (DadosEconomicoFinanceiros)", "leiaute", nullable=False
        ),
        Column(
            "block",
            pl.String,
            "asset block tag (TIT_PUB, COTAS, DEMAIS_CODIF...); APLICACAO in the legacy layout",
            "bloco",
            nullable=False,
        ),
        Column(
            "asset_type_code", pl.String, "COD_TP_ATIV as written (no code table verified)", "tipo do ativo (código)"
        ),
        Column("asset_type_text", pl.String, "legacy DescricaoTipoAtivo", "tipo do ativo (texto)"),
        Column("position_type_code", pl.String, "COD_TP_APLIC as written", "tipo da aplicação (código)"),
        Column("legacy_class", pl.String, "legacy Classificacao as written", "classificação (leiaute antigo)"),
        Column("asset_code", pl.String, "COD_ATIV / CodigoAtivo: ticker for shares", "código do ativo"),
        Column("asset_description", pl.String, "DESC of a non-coded asset", "descrição do ativo"),
        Column(
            "code_valid_from", pl.Date, "DT_INI_VIGEN / DataInicioVigenciaAtivo", "início da vigência do código", "date"
        ),
        Column("selic_code", pl.String, "COD_SELIC of a government bond", "código Selic"),
        Column(
            "held_fund_cnpj", pl.String, "COTAS/CNPJ_FDO: the fund whose quotas are held", "CNPJ do fundo investido"
        ),
        Column("issuer_tax_id", pl.String, "issuer CNPJ; null when the issuer is a natural person", "CNPJ do emissor"),
        Column("issuer_name", pl.String, "issuer name; null when the issuer is a natural person", "emissor"),
        Column("issuer_person_type", pl.String, "TP_PF_PJ_EMIS as written", "tipo de pessoa do emissor"),
        Column("maturity_date", pl.Date, "DT_VENC", "vencimento", "date"),
        Column("related_issuer", pl.String, "EMPR_LIGADA / EmpresaLigada: linked company (S/N)", "empresa ligada"),
        Column(
            "confidential_days",
            pl.Int32,
            "QTDE_DIAS_CONFID: days the position stays confidential",
            "dias de confidencialidade",
            "days",
        ),
        Column("trading_intent", pl.String, "TP_NEGOC as written", "tipo de negociação"),
        Column("is_postfixed", pl.String, "ST_TIT_POS_FIX (S/N)", "pós-fixado"),
        Column("index_code", pl.String, "TIT_POS_FIX_COD_INDEX", "indexador"),
        Column("index_percent", RATE, "TIT_POS_FIX_PR_INDEX", "percentual do indexador", "% of index"),
        Column("coupon_percent", RATE, "TIT_POS_FIX_CUPOM", "cupom", "% a.a. as written"),
        Column("prefixed_rate_percent", RATE, "TIT_PRE_FIX_TAXA_CONTR", "taxa contratada", "% a.a. as written"),
        Column("issuer_rated", pl.String, "ST_CLASSIF_RISCO (S/N)", "emissor classificado"),
        Column("rating_agency", pl.String, "AG_CLASSIF_RISCO", "agência de risco"),
        Column("rating_date", pl.Date, "DT_CLASSIF_RISCO", "data da classificação", "date"),
        Column("rating", pl.String, "GRAU_CLASSIF_RISCO", "classificação de risco"),
        Column("cetip_registered", pl.String, "ST_TIT_REG_CETIP (S/N)", "registrado na Cetip"),
        Column("has_guarantee", pl.String, "ST_TIT_GARANT_SEGURO (S/N)", "com garantia ou seguro"),
        Column("co_obligor_cnpj", pl.String, "CNPJ_INSTIT_FINANC", "CNPJ da instituição financeira"),
        Column("country_code", pl.String, "COD_PAIS (abroad)", "código do país"),
        Column("exchange_code", pl.String, "COD_BV_MERC (abroad)", "código da bolsa ou mercado"),
        Column("foreign_asset_code", pl.String, "COD_ATIVO_BV_MERC (abroad)", "código do ativo no exterior"),
        Column("sold_qty", QTY, "QTDE_VENDAS_NEGOC: quantity sold in the month", "quantidade vendida", "quantity"),
        Column("sold_brl", MONEY, "VL_VENDAS_NEGOC", "valor vendido", "BRL"),
        Column("bought_qty", QTY, "QTDE_AQUIS_NEGOC: quantity bought in the month", "quantidade comprada", "quantity"),
        Column("bought_brl", MONEY, "VL_AQUIS_NEGOC", "valor comprado", "BRL"),
        Column("final_qty", QTY, "QTDE_POS_FIM: quantity held at month end", "quantidade final", "quantity"),
        Column("market_value_brl", MONEY, "MERC_POS_FIM: market value at month end", "valor de mercado", "BRL"),
        Column("cost_value_brl", MONEY, "legacy Custo (empty in every document seen)", "valor de custo", "BRL"),
        Column("net_assets_percent", RATE, "legacy PercentualPatrimonio", "% do patrimônio líquido", "% of net assets"),
    ),
    rules=(
        Rule("cnpj_14_digits", pl.col("fund_cnpj").str.contains(r"^\d{14}$")),
        Rule("month_first_day", pl.col("reference_month").dt.day() == 1),
        Rule("layout_known", pl.col("layout").is_in(("cda", "legacy"))),
    ),
    key=("doc_id", "fund_cnpj", "line"),
)
NET_ASSETS = Contract(
    table="staging.b3_fundosnet_cda.net_assets",
    version=1,
    description="An ETF's net assets in the month-end portfolio document.",
    columns=(
        Column("doc_id", pl.Int64, "Fundos.NET document id", "id do documento", nullable=False),
        Column("fund_cnpj", pl.String, "CNPJ_FDO / CNPJFundo, 14 digits", "CNPJ", nullable=False),
        Column(
            "reference_month",
            pl.Date,
            "DT_COMPT MM/YYYY as the first day of the month",
            "competência",
            "date",
            nullable=False,
        ),
        Column("net_assets_brl", MONEY, "VL_PL / ValorPatrimonioLiquido", "patrimônio líquido", "BRL"),
        Column("generated_on", pl.Date, "DT_GERAC_ARQ / DataRecebeInformacoes", "data de geração do arquivo", "date"),
        Column("layout", pl.String, "cda or legacy", "leiaute", nullable=False),
    ),
    rules=(
        Rule("cnpj_14_digits", pl.col("fund_cnpj").str.contains(r"^\d{14}$")),
        Rule("month_first_day", pl.col("reference_month").dt.day() == 1),
    ),
    key=("doc_id", "fund_cnpj"),
)
LISTING = dataclasses.replace(fundosnet.LISTING, table="staging.b3_fundosnet_cda.listing")
CONTRACTS = {"position": POSITION, "net_assets": NET_ASSETS, "listing": LISTING}

# relative path inside an asset block -> position column (layout `cda`)
CDA_FIELDS: dict[str, str] = {
    "CNPJ_FDO": "held_fund_cnpj",
    "COD_SELIC": "selic_code",
    "DT_VENC": "maturity_date",
    "COD_TP_ATIV": "asset_type_code",
    "COD_ATIV": "asset_code",
    "DT_INI_VIGEN": "code_valid_from",
    "DESC": "asset_description",
    "NM_EMIS": "issuer_name",
    "EMIS/NM_EMIS": "issuer_name",
    "EMIS/NR_PF_PJ_EMIS": "issuer_tax_id",
    "EMIS/CNPJ_EMIS": "issuer_tax_id",
    "EMIS/TP_PF_PJ_EMIS": "issuer_person_type",
    "ST_CLASSIF_RISCO": "issuer_rated",
    "CLASSIF_RISCO/AG_CLASSIF_RISCO": "rating_agency",
    "CLASSIF_RISCO/DT_CLASSIF_RISCO": "rating_date",
    "CLASSIF_RISCO/GRAU_CLASSIF_RISCO": "rating",
    "ST_TIT_POS_FIX": "is_postfixed",
    "TIT_POS_FIX_INDEX/TIT_POS_FIX_COD_INDEX": "index_code",
    "TIT_POS_FIX_INDEX/TIT_POS_FIX_PR_INDEX": "index_percent",
    "TIT_POS_FIX_INDEX/TIT_POS_FIX_CUPOM": "coupon_percent",
    "TIT_PRE_FIX_TAXA_CONTR": "prefixed_rate_percent",
    "ST_TIT_REG_CETIP": "cetip_registered",
    "ST_TIT_GARANT_SEGURO": "has_guarantee",
    "CNPJ_INSTIT_FINANC": "co_obligor_cnpj",
    "COD_PAIS": "country_code",
    "COD_BV_MERC": "exchange_code",
    "COD_ATIVO_BV_MERC": "foreign_asset_code",
    "APLIC/COD_TP_APLIC": "position_type_code",
    "APLIC/EMPR_LIGADA": "related_issuer",
    "APLIC/QTDE_DIAS_CONFID": "confidential_days",
    "APLIC/NEGOC/TP_NEGOC": "trading_intent",
    "APLIC/NEGOC/QTDE_VENDAS_NEGOC": "sold_qty",
    "APLIC/NEGOC/VL_VENDAS_NEGOC": "sold_brl",
    "APLIC/NEGOC/QTDE_AQUIS_NEGOC": "bought_qty",
    "APLIC/NEGOC/VL_AQUIS_NEGOC": "bought_brl",
    "APLIC/POS_FIM/QTDE_POS_FIM": "final_qty",
    "APLIC/POS_FIM/MERC_POS_FIM": "market_value_brl",
}
CDA_BLOCKS = frozenset(
    {"TIT_PUB", "COTAS", "DEMAIS_CODIF", "DEMAIS_N_CODIF", "INV_EXT", "DEP_PRAZO_TIT_IF", "TIT_AGRO_CRED_PRIV"}
)
CDA_HEADER = frozenset({"COD_DOC", "VERSAO", "DT_COMPT", "DT_GERAC_ARQ"})
# legacy `Aplicacao` paths
LEGACY_FIELDS: dict[str, str] = {
    "Ativo/DescricaoTipoAtivo": "asset_type_text",
    "Ativo/CodigoAtivo": "asset_code",
    "Ativo/DataInicioVigenciaAtivo": "code_valid_from",
    "Ativo/CNPJEmissorAtivo": "issuer_tax_id",
    "Ativo/DenominacaoSocialEmissorAtivo": "issuer_name",
    "Classificacao": "legacy_class",
    "EmpresaLigada": "related_issuer",
    "NegocioRealizado/QtdeVendas": "sold_qty",
    "NegocioRealizado/ValorVendas": "sold_brl",
    "NegocioRealizado/QtdeAquisicoes": "bought_qty",
    "NegocioRealizado/ValorAquisicoes": "bought_brl",
    "PosicaoFinal/QtdePosicaoFinal": "final_qty",
    "PosicaoFinal/Custo": "cost_value_brl",
    "PosicaoFinal/ValorMercado": "market_value_brl",
    "PosicaoFinal/PercentualPatrimonio": "net_assets_percent",
}
LEGACY_HEADER = frozenset(
    {
        "Competencia",
        "Versao",
        "DataRecebeInformacoes",
        "CNPJFundo",
        "NomeFundo",
        "CNPJAdm",
        "NomeAdm",
        "ValorPatrimonioLiquido",
    }
)
CONTAINERS = frozenset({"APLIC/NEGOC", "NEGOC", "CLASSIF_RISCO", "EMIS", "TIT_POS_FIX_INDEX"})
DATES = {"code_valid_from", "maturity_date", "rating_date"}
DECIMALS = {c.name: c.dtype for c in POSITION.columns if isinstance(c.dtype, pl.Decimal)}
NUMBER = {"cda": re.compile(r"^-?\d+(?:,\d+)?$"), "legacy": re.compile(r"^-?\d+(?:\.\d+)?$")}


def _local(tag: str) -> str:
    return tag.rpartition("}")[2]


def _day(text: str, field: str) -> date:
    m = re.fullmatch(r"(\d\d)/(\d\d)/(\d{4})", text)
    if not m:
        raise LayoutError(f"CDA: {field}={text!r}")
    return date(int(m[3]), int(m[2]), int(m[1]))


def _cnpj(text: str) -> str:
    """A CNPJ written without its leading zeros (a spreadsheet artefact: 6175696000173 in id 1240750) is padded."""
    return text.zfill(14) if re.fullmatch(r"\d{12,13}", text) else text


def _month(text: str | None) -> date:
    m = re.fullmatch(r"(\d\d)/(\d{4})", text or "")
    if not m:
        raise LayoutError(f"CDA: competence {text!r}")
    return date(int(m[2]), int(m[1]), 1)


def _num(text: str, layout: str, scale: int, field: str) -> Decimal:
    if not NUMBER[layout].match(text):
        raise LayoutError(f"CDA: {field}={text!r}")
    sep = "," if layout == "cda" else "."
    if len(text.partition(sep)[2]) > scale:  # never round silently
        raise LayoutError(f"CDA: {field}={text!r} has more than {scale} decimals")
    return Decimal(text.replace(",", "."))


def _root(blob: bytes) -> ET.Element:
    head = blob.removeprefix(BOM).lstrip()
    if not head.startswith(b"<"):
        raise NotData(f"Fundos.NET body is not XML: {blob[:60]!r}")
    try:
        text = blob.decode("utf-8")
    except UnicodeDecodeError:
        return ET.fromstring(blob)  # a real single-byte document: trust its declaration
    if text.isascii():
        return ET.fromstring(blob)
    # valid UTF-8 with non-ASCII bytes is UTF-8 whatever the declaration says (id 1240750 declares Windows-1252)
    text = re.sub(r"^(\s*<\?xml[^>]*?)\s+encoding=(\"[^\"]*\"|'[^']*')", r"\1", text.removeprefix("﻿"), count=1)
    return ET.fromstring(text.encode("utf-8"))


def _leaves(el: ET.Element, prefix: str, allowed: dict[str, str], where: str) -> dict[str, str]:
    """{column: text} of the leaves under `el`, raising on a path that is not in `allowed`."""
    out: dict[str, str] = {}
    for c in el:
        path = f"{prefix}{_local(c.tag)}"
        if len(c):
            out.update(_leaves(c, path + "/", allowed, where))
            continue
        if path in CONTAINERS and not (c.text or "").strip():
            continue  # an empty <NEGOC/> declares nothing
        if path not in allowed:
            raise LayoutError(f"CDA: unknown element {where}/{path}")
        col = allowed[path]
        if col in out:
            raise LayoutError(f"CDA: {where}/{path} repeated")
        text = (c.text or "").strip()
        if text:
            out[col] = text
    return out


def _row(f: dict[str, str], layout: str, doc: dict[str, Any], line: int, block: str, locator: str) -> dict[str, Any]:
    person = f.get("issuer_person_type") == "PF" or re.fullmatch(r"\d{11}", f.get("issuer_tax_id", "")) is not None
    row: dict[str, Any] = {c.name: None for c in POSITION.columns}
    row |= doc | {"line": line, "layout": layout, "block": block, "raw_locator": locator}
    for k, v in f.items():
        if person and k in ("issuer_tax_id", "issuer_name"):
            continue  # a natural person's CPF and name are never kept
        if k in DATES:
            row[k] = _day(v, k)
        elif k in DECIMALS:
            row[k] = _num(v, layout, DECIMALS[k].scale, k)  # type: ignore[union-attr]
        elif k == "confidential_days":
            row[k] = int(v)
        elif k in ("held_fund_cnpj", "co_obligor_cnpj", "issuer_tax_id"):
            row[k] = _cnpj(v)
        else:
            row[k] = v
    return row


def _net(
    doc_id: int, cnpj: str, month: date, layout: str, text: str, generated: date | None, locator: str
) -> dict[str, Any]:
    return {
        "doc_id": doc_id, "fund_cnpj": cnpj, "reference_month": month, "layout": layout,
        "net_assets_brl": _num(text, layout, 4, "net assets") if text else None,
        "generated_on": generated, "raw_locator": locator,
    }  # fmt: skip


def parse_cda(blob: bytes, row: dict[str, Any]) -> tuple[pl.DataFrame, pl.DataFrame]:
    """(positions, net assets) of one document."""
    root = _root(blob)
    doc_id = fundosnet.doc_id_of(row)
    pos: list[dict[str, Any]] = []
    nets: list[dict[str, Any]] = []
    name = _local(root.tag)
    if name == "DOC_ARQ":
        if root.find("*//{*}APLIC_ATIVO") is not None or root.find("LISTA_INFORM/APLIC_ATIVO") is not None:
            raise NotData("Fundos.NET type 63 document of a FIDC (APLIC_ATIVO), not an ETF portfolio")
        layout = "cda"
        kids = [_local(c.tag) for c in root]
        if kids != ["CAB_INFORM", "LISTA_INFORM"]:
            raise LayoutError(f"CDA: DOC_ARQ children {kids}")
        head = {_local(c.tag): (c.text or "").strip() for c in root[0]}
        if set(head) - CDA_HEADER or "DT_COMPT" not in head:
            raise LayoutError(f"CDA: CAB_INFORM {sorted(head)}")
        month = _month(head["DT_COMPT"])
        generated = _day(head["DT_GERAC_ARQ"], "DT_GERAC_ARQ") if head.get("DT_GERAC_ARQ") else None
        for i, inf in enumerate(root[1], start=1):
            if _local(inf.tag) != "INFORM":
                raise LayoutError(f"CDA: LISTA_INFORM holds {_local(inf.tag)}")
            tags = [_local(c.tag) for c in inf]
            if tags != ["CNPJ_FDO", "VL_PL", "LISTA_ATIV"]:
                raise LayoutError(f"CDA: INFORM children {tags}")
            cnpj = _cnpj((inf[0].text or "").strip())
            where = f"LISTA_INFORM/INFORM[{i}]"
            nets.append(_net(doc_id, cnpj, month, layout, (inf[1].text or "").strip(), generated, where + "/VL_PL"))
            base = {"doc_id": doc_id, "fund_cnpj": cnpj, "reference_month": month}
            for j, blk in enumerate(inf[2], start=1):
                tag = _local(blk.tag)
                if tag not in CDA_BLOCKS:
                    raise LayoutError(f"CDA: unknown asset block {tag}")
                loc = f"{where}/LISTA_ATIV/{tag}[{j}]"
                f = _leaves(blk, "", CDA_FIELDS, loc)
                if len(blk.findall("{*}APLIC")) != 1:
                    raise LayoutError(f"CDA: {loc} holds {len(blk.findall('{*}APLIC'))} APLIC")
                pos.append(_row(f, layout, base, len(pos) + 1, tag, loc))
    elif name == "DadosEconomicoFinanceiros":
        layout = "legacy"
        kids = [_local(c.tag) for c in root]
        if kids != ["DadosGerais", "Carteira"]:
            raise LayoutError(f"CDA: legacy children {kids}")
        g = {_local(c.tag): (c.text or "").strip() for c in root[0]}
        if set(g) - LEGACY_HEADER or not {"Competencia", "CNPJFundo"} <= set(g):
            raise LayoutError(f"CDA: DadosGerais {sorted(g)}")
        month = _month(g["Competencia"])
        cnpj = _cnpj(g["CNPJFundo"])
        received = g.get("DataRecebeInformacoes")
        nets.append(
            _net(
                doc_id,
                cnpj,
                month,
                layout,
                g.get("ValorPatrimonioLiquido", ""),
                _day(received, "DataRecebeInformacoes") if received else None,
                "DadosGerais/ValorPatrimonioLiquido",
            )
        )
        cart = root[1]
        if [_local(c.tag) for c in cart] != ["Aplicacoes"]:
            raise LayoutError("CDA: legacy Carteira children")
        base = {"doc_id": doc_id, "fund_cnpj": cnpj, "reference_month": month}
        for j, ap in enumerate(cart[0], start=1):
            if _local(ap.tag) != "Aplicacao":
                raise LayoutError(f"CDA: Aplicacoes holds {_local(ap.tag)}")
            loc = f"Carteira/Aplicacoes/Aplicacao[{j}]"
            pos.append(_row(_leaves(ap, "", LEGACY_FIELDS, loc), layout, base, j, "APLICACAO", loc))
    else:
        raise LayoutError(f"CDA: root {root.tag}")
    prov = (pl.lit(row["raw_sha256"]).alias("raw_sha256"), pl.lit(row["ingest_run_id"]).alias("ingest_run_id"))
    pschema = {c.name: c.dtype for c in POSITION.columns} | {"raw_locator": pl.String}
    nschema = {c.name: c.dtype for c in NET_ASSETS.columns} | {"raw_locator": pl.String}
    return (
        pl.DataFrame(pos, schema=pschema, orient="row").with_columns(*prov),
        pl.DataFrame(nets, schema=nschema, orient="row").with_columns(*prov),
    )


def parse_payload(blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
    ds = str(row["dataset_id"])
    if ds == "carteira":
        positions, net_assets = parse_cda(blob, row)
        part = f"id_block={fundosnet.doc_id_of(row) // 100_000}"
        yield Parsed("position", part, positions)
        yield Parsed("net_assets", part, net_assets)
    elif ds == "listagem":
        yield Parsed("listing", "all", fundosnet.parse_listing(blob, row))
    else:
        raise LayoutError(f"CDA: dataset {ds}")
