"""CVM fund open data: FII reports (`cvm_fii`), daily fund NAV (`cvm_fi_inf_diario`) and portfolios (`cvm_fi_cda`).

One table-driven parser serves the three sources (docs/sources/cvm_fii.md, cvm_fi_inf_diario.md, cvm_fi_cda.md).
All members are cp1252 (ASCII-only ones trivially), `;` separated, CRLF, ISO dates, `.` decimals, some values in
exponent notation. A member is parsed only against a header table: legacy and CVM-175 headers are normalised through
`ALIASES`, optional columns may be absent, anything else raises `LayoutError`. A non-empty value that does not cast to
its declared type (or has more decimals than the declared scale) also raises: nothing is nulled or rounded silently.

Not parsed, on purpose: contact data (addresses, phones, e-mails, directors, their CPF); the CPF and name of a natural
person issuer in CDA; members that are not fund-level positions (`cda_fiim`, `cda_fie`, `*CONFID*`, FII annual and
the other quarterly members). Fund names are kept once per table that identifies the fund, not on every position.
"""

from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, ClassVar

import polars as pl

from fin.config import Zones
from fin.ingest.base import Connector, Mode, Parsed
from fin.ingest.fetch import FetchSpec
from fin.ingest.snapshots import held_rows, today_brt
from fin.schema import Column, Contract, Rule

BASE = "https://dados.cvm.gov.br/dados"
FRACTION = "fraction (0.01 = 1%)"
QUOTAS = "quotas, as written (some filings carry fractions of a quota)"

# kind -> (dtype, default unit)
KINDS: dict[str, tuple[Any, str]] = {
    "str": (pl.String, ""),
    "date": (pl.Date, "date"),
    "int": (pl.Int64, "count"),
    "i16": (pl.Int16, ""),
    "brl": (pl.Decimal(38, 2), "BRL"),
    "brlw": (pl.Decimal(38, 16), "BRL"),  # nvarchar sources (FII): float noise beyond the cents is kept as written
    "qty": (pl.Decimal(38, 6), "units"),
    "quota": (pl.Decimal(38, 12), "BRL per quota"),
    "ratio": (pl.Decimal(38, 20), FRACTION),
    "pct": (pl.Decimal(38, 6), "% as written"),
    "wide": (pl.Decimal(38, 20), "as written"),
}
ALIASES = {  # legacy (pre CVM 175) header names -> the current ones
    "CNPJ_Fundo": "CNPJ_Fundo_Classe",
    "Nome_Fundo": "Nome_Fundo_Classe",
    "TP_FUNDO": "TP_FUNDO_CLASSE",
    "CNPJ_FUNDO": "CNPJ_FUNDO_CLASSE",
    "CNPJ_FUNDO_COTA": "CNPJ_FUNDO_CLASSE_COTA",
    "NM_FUNDO_COTA": "NM_FUNDO_CLASSE_SUBCLASSE_COTA",
}


class LayoutError(ValueError):
    pass


@dataclass(frozen=True)
class Field:
    src: str
    name: str
    kind: str
    en: str
    unit: str = ""
    required: bool = False  # not null (a key part)


def _f(src: str, name: str, kind: str, en: str, unit: str = "", required: bool = False) -> Field:
    return Field(src, name, kind, en, unit, required)


@dataclass(frozen=True)
class Table:
    header: Sequence[str]  # every column of the member, current names, in file order
    optional: frozenset[str]  # header columns that older/newer files may lack
    fields: tuple[Field, ...]  # the columns kept
    description: str
    rules: tuple[Rule, ...] = ()


def _contract(source: str, dataset: str, t: Table, extra: tuple[Field, ...] = ()) -> Contract:
    cols = tuple(
        Column(
            f.name,
            KINDS[f.kind][0],
            f.en,
            f.src,
            f.unit or KINDS[f.kind][1],
            nullable=not f.required,
        )
        for f in t.fields + extra
    )
    return Contract(f"staging.{source}.{dataset}", 1, t.description, cols, t.rules)


def _expr(f: Field) -> pl.Expr:
    c = pl.col(f.src).str.strip_chars()
    dtype = KINDS[f.kind][0]
    if f.kind == "str":
        return pl.col(f.src).alias(f.name)
    if f.kind == "date":
        return c.str.strptime(pl.Date, "%Y-%m-%d", strict=False).alias(f.name)
    return c.cast(dtype, strict=False).alias(f.name)


def _check_casts(df: pl.DataFrame, fields: Iterable[Field], name: str) -> None:
    """Fail loudly when a typed column lost a value (did not cast) or would be rounded (more decimals than scale)."""
    typed = [f for f in fields if f.kind != "str" and f.src in df.columns]
    for f in typed:
        s = df[f.src].str.strip_chars()
        present = s.str.len_chars() > 0
        out = df.select(_expr(f))[f.name]
        lost = int((present & out.is_null()).sum())
        if lost:
            sample = s.filter(present & out.is_null()).head(3).to_list()
            raise LayoutError(f"{name}: {lost} values of {f.src} do not cast to {f.kind}, e.g. {sample}")
        dtype = KINDS[f.kind][0]
        if isinstance(dtype, pl.Decimal):
            more = s.str.contains(rf"^-?\d*\.\d{{{dtype.scale + 1},}}$")
            if more.any():
                raise LayoutError(
                    f"{name}: {f.src} has more than {dtype.scale} decimals, e.g. {s.filter(more).head(2).to_list()}"
                )


def _decode(data: bytes) -> str:
    try:
        return data.decode("cp1252")
    except UnicodeDecodeError:  # cp1252 leaves five bytes undefined; latin-1 keeps them as C1 controls
        return data.decode("latin-1")


def parse_csv(
    data: bytes, name: str, t: Table, row: dict[str, Any], select: Iterable[Field] | None = None
) -> pl.DataFrame:
    """The member as a typed frame: kept columns, then the three provenance columns. Header checked against `t`."""
    text = _decode(data)
    head = [ALIASES.get(h, h) for h in text.split("\n", 1)[0].rstrip("\r").split(";")]
    expected = [h for h in t.header if h in head or h not in t.optional]
    if head != expected:
        raise LayoutError(f"{name}: header changed: {head}")
    df = pl.read_csv(io.StringIO(text), separator=";", infer_schema=False, quote_char=None, new_columns=head)
    fields = tuple(select if select is not None else t.fields)
    present = [f for f in fields if f.src in df.columns]
    _check_casts(df, present, name)
    cols = [_expr(f) for f in present] + [
        pl.lit(None, dtype=KINDS[f.kind][0]).alias(f.name) for f in fields if f.src not in df.columns
    ]
    out = df.with_row_index("i", offset=2).select(
        *cols,
        pl.lit(row["raw_sha256"]).alias("raw_sha256"),
        (pl.lit(f"member={name};line=") + pl.col("i").cast(pl.String)).alias("raw_locator"),
        pl.lit(row["ingest_run_id"]).alias("ingest_run_id"),
    )
    return out.select([f.name for f in fields] + ["raw_sha256", "raw_locator", "ingest_run_id"])


def _members(blob: bytes, row: dict[str, Any]) -> Iterator[tuple[str, bytes]]:
    notes = row.get("notes") or ""
    if "|" in notes:  # an unpacked member (ADR-0014)
        yield notes.split("|", 1)[1], blob
    elif blob[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            for n in z.namelist():
                yield n, z.read(n)
    # else: the JSON record of an unpacked zip


def _nonneg(col: str) -> Rule:
    return Rule(f"{col}_not_negative", (pl.col(col) >= 0) | pl.col(col).is_null())


def _period(token: str) -> str:
    return f"month={token}" if len(token) == 6 else f"year={token}"


# ---------------------------------------------------------------------------------------------------------- FII
def _key() -> tuple[Field, ...]:
    return (
        _f("CNPJ_Fundo_Classe", "cnpj", "str", "fund/class CNPJ as written", required=True),
        _f(
            "Data_Referencia",
            "reference_date",
            "date",
            "reference date of the report (1st of the month for monthly)",
            required=True,
        ),
        _f("Versao", "version", "i16", "version of the document; a higher one restates the lower", "", True),
    )


GENERAL_HEADER = [
    "Tipo_Fundo_Classe",
    "CNPJ_Fundo_Classe",
    "Data_Referencia",
    "Versao",
    "Data_Entrega",
    "Nome_Fundo_Classe",
    "Data_Funcionamento",
    "Publico_Alvo",
    "Codigo_ISIN",
    "Quantidade_Cotas_Emitidas",
    "Fundo_Exclusivo",
    "Fundo_Nao_Listado_Exclusivo",
    "Cotistas_Vinculo_Familiar",
    "Mandato",
    "Segmento_Atuacao",
    "Tipo_Gestao",
    "Prazo_Duracao",
    "Data_Prazo_Duracao",
    "Encerramento_Exercicio_Social",
    "Mercado_Negociacao_Bolsa",
    "Mercado_Negociacao_MBO",
    "Mercado_Negociacao_MB",
    "Entidade_Administradora_BVMF",
    "Entidade_Administradora_CETIP",
    "Nome_Administrador",
    "CNPJ_Administrador",
    "Logradouro",
    "Numero",
    "Complemento",
    "Bairro",
    "Cidade",
    "Estado",
    "CEP",
    "Telefone1",
    "Telefone2",
    "Telefone3",
    "Site",
    "Email",
    "Data_Encerramento_Trimestre",
]
GENERAL = Table(
    GENERAL_HEADER,
    frozenset({"Tipo_Fundo_Classe", "Fundo_Nao_Listado_Exclusivo", "Data_Encerramento_Trimestre"}),
    (
        _f("Tipo_Fundo_Classe", "fund_type", "str", "fund or class (CVM 175)"),
        *_key(),
        _f("Data_Entrega", "delivered_on", "date", "date CVM received the document (knowledge time)"),
        _f("Nome_Fundo_Classe", "fund_name", "str", "registered name"),
        _f("Data_Funcionamento", "started_on", "date", "start of operation"),
        _f("Publico_Alvo", "target_audience", "str", "target audience"),
        _f("Codigo_ISIN", "isin", "str", "ISIN of the quota"),
        _f("Quantidade_Cotas_Emitidas", "quotas_issued", "wide", "quotas issued", QUOTAS),
        _f("Fundo_Exclusivo", "exclusive_fund", "str", "exclusive fund flag, as written (S/N or Sim/Nao)"),
        _f("Fundo_Nao_Listado_Exclusivo", "unlisted_exclusive_fund", "str", "unlisted exclusive flag"),
        _f("Cotistas_Vinculo_Familiar", "family_holders", "str", "holders with family ties flag"),
        _f("Mandato", "mandate", "str", "mandate"),
        _f("Segmento_Atuacao", "segment", "str", "segment (Shoppings, Lajes, Multicategoria...)"),
        _f("Tipo_Gestao", "management_type", "str", "active or passive management"),
        _f("Prazo_Duracao", "term", "str", "term (Indeterminado or a period)"),
        _f("Data_Prazo_Duracao", "term_end_date", "date", "end of the term"),
        _f("Encerramento_Exercicio_Social", "fiscal_year_end", "str", "fiscal year end, dd/mm"),
        _f("Mercado_Negociacao_Bolsa", "traded_on_exchange", "str", "quotas traded on exchange flag"),
        _f("Mercado_Negociacao_MBO", "traded_otc_organised", "str", "organised OTC (MBO) flag"),
        _f("Mercado_Negociacao_MB", "traded_otc", "str", "OTC (MB) flag"),
        _f("Entidade_Administradora_BVMF", "market_operator_b3", "str", "market operator is B3 flag"),
        _f("Entidade_Administradora_CETIP", "market_operator_cetip", "str", "market operator is CETIP flag"),
        _f("Nome_Administrador", "administrator_name", "str", "administrator (a company)"),
        _f("CNPJ_Administrador", "administrator_cnpj", "str", "administrator CNPJ as written"),
        _f("Data_Encerramento_Trimestre", "quarter_end_date", "date", "end of the quarter (quarterly report)"),
    ),
    "General data of an FII report: identity, ISIN, segment, administrator, delivery date.",
)

_HOLDERS = (
    ("Total_Numero_Cotistas", "holders_total", "all holders"),
    ("Numero_Cotistas_Pessoa_Fisica", "holders_individuals", "individuals"),
    ("Numero_Cotistas_Pessoa_Juridica_Nao_Financeira", "holders_nonfinancial_companies", "non-financial companies"),
    ("Numero_Cotistas_Banco_Comercial", "holders_commercial_banks", "commercial banks"),
    ("Numero_Cotistas_Corretora_Distribuidora", "holders_brokers_dealers", "brokers and dealers"),
    ("Numero_Cotistas_Outras_Pessoas_Juridicas_Financeira", "holders_other_financial", "other financial companies"),
    ("Numero_Cotistas_Investidores_Nao_Residentes", "holders_non_residents", "non-resident investors"),
    ("Numero_Cotistas_Entidade_Aberta_Previdencia_Complementar", "holders_open_pension", "open pension entities"),
    ("Numero_Cotistas_Entidade_Fechada_Previdência_Complementar", "holders_closed_pension", "closed pension entities"),
    (
        "Numero_Cotistas_Regime_Proprio_Previdencia_Servidores_Publicos",
        "holders_public_pension",
        "public servants' schemes",
    ),
    ("Numero_Cotistas_Sociedade_Seguradora_Resseguradora", "holders_insurers", "insurers"),
    (
        "Numero_Cotistas_Sociedade_Capitalizacao_Arrendamento_Mercantil",
        "holders_capitalization_leasing",
        "capitalisation and leasing",
    ),
    ("Numero_Cotistas_FII", "holders_fii", "FII holders"),
    ("Numero_Cotistas_Outros_Fundos", "holders_other_funds", "other funds"),
    ("Numero_Cotistas_Distribuidores_Fundo", "holders_distributors", "fund distributors"),
    ("Numero_Cotistas_Outros_Tipos", "holders_other", "other types"),
)
_SUMMARY_TAIL = (
    ("Valor_Ativo", "total_assets_brl", "brlw", "total assets"),
    ("Patrimonio_Liquido", "net_assets_brl", "brlw", "net asset value (patrimonio liquido)"),
    ("Cotas_Emitidas", "quotas_issued", "wide", "quotas issued"),
    ("Valor_Patrimonial_Cotas", "nav_per_quota_brl", "wide", "net asset value per quota (valor patrimonial)"),
    (
        "Percentual_Despesas_Taxa_Administracao",
        "management_fee_expense_ratio",
        "ratio",
        "management fee expense / net assets of the month",
    ),
    (
        "Percentual_Despesas_Agente_Custodiante",
        "custodian_fee_expense_ratio",
        "ratio",
        "custodian expense / net assets of the month",
    ),
    (
        "Percentual_Rentabilidade_Efetiva_Mes",
        "return_effective_month",
        "ratio",
        "effective return of the month (income basis)",
    ),
    ("Percentual_Rentabilidade_Patrimonial_Mes", "return_nav_month", "ratio", "NAV return of the month"),
    ("Percentual_Dividend_Yield_Mes", "dividend_yield_month", "ratio", "dividend yield of the month"),
    ("Percentual_Amortizacao_Cotas_Mes", "quota_amortization_month", "ratio", "quota amortisation of the month"),
)
SUMMARY = Table(
    tuple(
        ["CNPJ_Fundo_Classe", "Data_Referencia", "Versao", "Data_Informacao_Numero_Cotistas"]
        + [h for h, *_ in _HOLDERS]
        + [h for h, *_ in _SUMMARY_TAIL]
    ),
    frozenset(),
    (
        *_key(),
        _f("Data_Informacao_Numero_Cotistas", "holders_as_of", "date", "date of the holder count"),
        *(_f(h, n, "int", f"number of holders: {d}", "holders") for h, n, d in _HOLDERS),
        *(
            _f(
                h,
                n,
                k,
                d,
                "BRL"
                if k == "brlw"
                else ("BRL per quota" if n == "nav_per_quota_brl" else (QUOTAS if n == "quotas_issued" else "")),
            )
            for h, n, k, d in _SUMMARY_TAIL
        ),
    ),
    "FII monthly summary: NAV, NAV per quota, quotas, holders by type, return and yield of the month.",
    (_nonneg("quotas_issued"),),  # net assets can be negative (liabilities above assets): kept
)

_BALANCE = [
    ("Total_Necessidades_Liquidez", "liquidity_needs_total_brl"),
    ("Disponibilidades", "cash_brl"),
    ("Titulos_Publicos", "government_bonds_brl"),
    ("Titulos_Privados", "private_securities_brl"),
    ("Fundos_Renda_Fixa", "fixed_income_funds_brl"),
    ("Total_Investido", "total_invested_brl"),
    ("Direitos_Bens_Imoveis", "real_estate_rights_brl"),
    ("Terrenos", "land_brl"),
    ("Imoveis_Renda_Acabados", "income_properties_built_brl"),
    ("Imoveis_Renda_Construcao", "income_properties_under_construction_brl"),
    ("Imoveis_Venda_Acabados", "for_sale_properties_built_brl"),
    ("Imoveis_Venda_Construcao", "for_sale_properties_under_construction_brl"),
    ("Outros_Direitos_Reais", "other_real_rights_brl"),
    ("Acoes", "equities_brl"),
    ("Debentures", "debentures_brl"),
    ("Bonus_Subscricao", "subscription_warrants_brl"),
    ("Certificados_Deposito_Valores_Mobiliarios", "securities_deposit_certificates_brl"),
    ("Cedulas_Debentures", "debenture_notes_brl"),
    ("Fundo_Acoes", "equity_funds_brl"),
    ("FIP", "fip_brl"),
    ("FII", "fii_brl"),
    ("FDIC", "fidc_brl"),
    ("Outras_Cotas_FI", "other_fund_quotas_brl"),
    ("Notas_Promissorias", "promissory_notes_brl"),
    ("Acoes_Sociedades_Atividades_FII", "shares_fii_activity_companies_brl"),
    ("Cotas_Sociedades_Atividades_FII", "quotas_fii_activity_companies_brl"),
    ("CEPAC", "cepac_brl"),
    ("CRI", "cri_brl"),
    ("CRI_CRA", "cri_cra_brl"),
    ("Letras_Hipotecarias", "mortgage_bills_brl"),
    ("LCI", "lci_brl"),
    ("LCI_LCA", "lci_lca_brl"),
    ("LIG", "lig_brl"),
    ("Outros_Valores_Mobliarios", "other_securities_brl"),
    ("Valores_Receber", "receivables_total_brl"),
    ("Contas_Receber_Aluguel", "rent_receivable_brl"),
    ("Contas_Receber_Venda_Imoveis", "property_sales_receivable_brl"),
    ("Outros_Valores_Receber", "other_receivables_brl"),
    ("Rendimentos_Distribuir", "distributions_payable_brl"),
    ("Taxa_Administracao_Pagar", "management_fee_payable_brl"),
    ("Taxa_Performance_Pagar", "performance_fee_payable_brl"),
    ("Obrigacoes_Aquisicao_Imoveis", "property_purchase_obligations_brl"),
    ("Adiantamento_Venda_Imoveis", "property_sale_advances_brl"),
    ("Adiantamento_Alugueis", "rent_advances_brl"),
    ("Obrigacoes_Securitizacao_Recebiveis", "receivables_securitisation_obligations_brl"),
    ("Instrumentos_Financeiros_Derivativos", "derivatives_brl"),
    ("Provisoes_Contigencias", "contingency_provisions_brl"),
    ("Outros_Valores_Pagar", "other_payables_brl"),
    ("Total_Passivo", "total_liabilities_brl"),
]
BALANCE = Table(
    tuple(["CNPJ_Fundo_Classe", "Data_Referencia", "Versao"] + [h for h, _ in _BALANCE]),
    frozenset({"CRI_CRA", "LCI_LCA"}),  # absent in the 2016-2018 files
    (*_key(), *(_f(h, n, "brlw", n.removesuffix("_brl").replace("_", " ")) for h, n in _BALANCE)),
    "FII monthly balance sheet (assets by type, payables), BRL.",
)

_LOSS = "ratio as written; a fraction in the 2026 files (0.1 = 10%), not guaranteed for every filing"
PROPERTY = Table(
    [
        "CNPJ_Fundo_Classe",
        "Data_Referencia",
        "Versao",
        "Classe",
        "Nome_Imovel",
        "Endereco",
        "Area",
        "Numero_Unidades",
        "Outras_Caracteristicas_Relevantes",
        "Percentual_Vacancia",
        "Percentual_Inadimplencia",
        "Percentual_Receitas_FII",
        "Percentual_Locado",
        "Percentual_Vendido",
        "Percentual_Conclusao_Obras_Realizado",
        "Percentual_Conclusao_Obras_Previsto",
        "Custo_Construcao_Realizado",
        "Custo_Construcao_Previsto",
        "Percentual_Imovel_Total_Investido",
    ],
    frozenset(),
    (
        *_key(),
        _f("Classe", "property_class", "str", "property class (income, for sale, under construction...)"),
        _f("Nome_Imovel", "property_name", "str", "property name"),
        _f("Endereco", "address", "str", "property address"),
        _f("Area", "area_m2", "wide", "area", "m2"),
        _f("Numero_Unidades", "units", "wide", "number of units", "units"),
        _f("Percentual_Vacancia", "vacancy_ratio", "wide", "vacancy", _LOSS),
        _f("Percentual_Inadimplencia", "delinquency_ratio", "wide", "delinquency", _LOSS),
        _f("Percentual_Receitas_FII", "fund_revenue_share", "wide", "share of the fund's revenue", _LOSS),
        _f("Percentual_Locado", "leased_ratio", "wide", "leased share", _LOSS),
        _f("Percentual_Vendido", "sold_ratio", "wide", "sold share", _LOSS),
        _f("Percentual_Conclusao_Obras_Realizado", "works_done_ratio", "wide", "works completed", _LOSS),
        _f("Percentual_Conclusao_Obras_Previsto", "works_planned_ratio", "wide", "works planned", _LOSS),
        _f("Custo_Construcao_Realizado", "construction_cost_done_brl", "brlw", "construction cost incurred"),
        _f("Custo_Construcao_Previsto", "construction_cost_planned_brl", "brlw", "construction cost planned"),
        _f("Percentual_Imovel_Total_Investido", "share_of_invested", "wide", "share of total invested", _LOSS),
    ),
    "FII quarterly real-estate holdings with vacancy, delinquency and leasing.",
)
ASSET = Table(
    [
        "CNPJ_Fundo_Classe",
        "Data_Referencia",
        "Versao",
        "Tipo",
        "Emissor",
        "CNPJ_Emissor",
        "Emissao",
        "Serie",
        "Codigo_Acao",
        "Nome_Ativo",
        "Data_Vencimento",
        "Quantidade",
        "Valor",
    ],
    frozenset(),
    (
        *_key(),
        _f("Tipo", "asset_type", "str", "type of the security"),
        _f("Emissor", "issuer_name", "str", "issuer name"),
        _f("CNPJ_Emissor", "issuer_cnpj", "str", "issuer CNPJ as written (digits only, leading zeros may be missing)"),
        _f("Emissao", "issue", "str", "issue"),
        _f("Serie", "series", "str", "series"),
        _f("Codigo_Acao", "ticker", "str", "share code"),
        _f("Nome_Ativo", "asset_name", "str", "asset name"),
        _f("Data_Vencimento", "maturity_date", "date", "maturity"),
        _f("Quantidade", "quantity", "wide", "quantity held", "units"),
        _f("Valor", "value_brl", "brlw", "carrying value"),
    ),
    "FII quarterly securities (shares, CRI, fund quotas...) with quantity and value.",
)

FII_MEMBERS: dict[str, tuple[str, Table]] = {  # member stem -> (dataset, table)
    "inf_mensal_fii_geral": ("monthly_general", GENERAL),
    "inf_mensal_fii_complemento": ("monthly_summary", SUMMARY),
    "inf_mensal_fii_ativo_passivo": ("monthly_balance", BALANCE),
    "inf_trimestral_fii_geral": ("quarterly_general", GENERAL),
    "inf_trimestral_fii_imovel": ("quarterly_property", PROPERTY),
    "inf_trimestral_fii_ativo": ("quarterly_asset", ASSET),
    "inf_anual_fii_geral": ("annual_general", GENERAL),
}
FII_CONTRACTS = {ds: _contract("cvm_fii", ds, t) for ds, t in FII_MEMBERS.values()}


def parse_fii(blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
    for name, data in _members(blob, row):
        m = re.fullmatch(r"(inf_(?:mensal|trimestral|anual)_fii_[a-z_]+?)_(\d{4})\.csv", name)
        if not m or m.group(1) not in FII_MEMBERS:
            continue
        ds, table = FII_MEMBERS[m.group(1)]
        yield Parsed(ds, f"year={m.group(2)}", parse_csv(data, name, table, row))


# ---------------------------------------------------------------------------------------------- daily fund NAV
DAILY = Table(
    [
        "TP_FUNDO_CLASSE",
        "CNPJ_FUNDO_CLASSE",
        "ID_SUBCLASSE",
        "DT_COMPTC",
        "VL_TOTAL",
        "VL_QUOTA",
        "VL_PATRIM_LIQ",
        "CAPTC_DIA",
        "RESG_DIA",
        "NR_COTST",
    ],
    frozenset({"TP_FUNDO_CLASSE", "ID_SUBCLASSE"}),  # absent before 2021 (HIST) and, ID_SUBCLASSE, before 2023-12
    (
        _f(
            "TP_FUNDO_CLASSE",
            "fund_type",
            "str",
            "fund type (legacy TP_FUNDO: FI, FIC-FI, FITVM...; CVM 175: CLASSES - FIF...)",
        ),
        _f("CNPJ_FUNDO_CLASSE", "cnpj", "str", "fund (legacy) or class (CVM 175) CNPJ as written", required=True),
        _f("ID_SUBCLASSE", "subclass_id", "str", "subclass identifier (CVM 175), empty for a class without subclasses"),
        _f("DT_COMPTC", "reference_date", "date", "competence date (the day the NAV refers to)", required=True),
        _f("VL_TOTAL", "portfolio_value_brl", "brl", "total value of the portfolio"),
        _f("VL_QUOTA", "quota_value_brl", "quota", "quota value (valor da cota)"),
        _f("VL_PATRIM_LIQ", "net_assets_brl", "brl", "net asset value (patrimonio liquido)"),
        _f("CAPTC_DIA", "subscriptions_brl", "brl", "subscriptions of the day (captacao)"),
        _f("RESG_DIA", "redemptions_brl", "brl", "redemptions of the day (resgates)"),
        _f("NR_COTST", "holders", "int", "number of quota holders", "holders"),
    ),
    "Daily NAV, quota value, subscriptions, redemptions and holders per fund (or class/subclass).",
    (_nonneg("holders"),),  # a negative quota is real: 32 funds had negative net assets in 2026-09
)
DAILY_CONTRACTS = {"daily": _contract("cvm_fi_inf_diario", "daily", DAILY)}


def parse_inf_diario(blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
    for name, data in _members(blob, row):
        m = re.fullmatch(r"inf_diario_fi_(\d{6}|\d{4})\.csv", name)
        if m:
            yield Parsed("daily", _period(m.group(1)), parse_csv(data, name, DAILY, row))


# ---------------------------------------------------------------------------------------------- CDA portfolios
_BASE = [
    "TP_FUNDO_CLASSE",
    "CNPJ_FUNDO_CLASSE",
    "DENOM_SOCIAL",
    "DT_COMPTC",
    "TP_APLIC",
    "TP_ATIVO",
    "EMISSOR_LIGADO",
    "TP_NEGOC",
    "QT_VENDA_NEGOC",
    "VL_VENDA_NEGOC",
    "QT_AQUIS_NEGOC",
    "VL_AQUIS_NEGOC",
    "QT_POS_FINAL",
    "VL_MERC_POS_FINAL",
    "VL_CUSTO_POS_FINAL",
    "DT_CONFID_APLIC",
]
_BLOCKS = {
    1: "TP_TITPUB CD_ISIN CD_SELIC DT_EMISSAO DT_VENC",
    2: "CNPJ_FUNDO_CLASSE_COTA ID_SUBCLASSE NM_FUNDO_CLASSE_SUBCLASSE_COTA",
    3: "CD_SWAP DS_SWAP",
    4: "CD_ATIVO DS_ATIVO CD_ISIN DT_INI_VIGENCIA DT_FIM_VIGENCIA",
    5: "CNPJ_EMISSOR EMISSOR DT_VENC TITULO_POSFX CD_INDEXADOR_POSFX DS_INDEXADOR_POSFX PR_INDEXADOR_POSFX PR_CUPOM_POSFX PR_TAXA_PREFX RISCO_EMISSOR AG_RISCO DT_RISCO GRAU_RISCO",  # noqa: E501
    6: "PF_PJ_EMISSOR CPF_CNPJ_EMISSOR EMISSOR DT_VENC TITULO_POSFX CD_INDEXADOR_POSFX DS_INDEXADOR_POSFX PR_INDEXADOR_POSFX PR_CUPOM_POSFX PR_TAXA_PREFX TITULO_CETIP TITULO_GARANTIA CNPJ_INSTITUICAO_FINANC_COOBR",  # noqa: E501
    7: "INVEST_COLETIVO INVEST_COLETIVO_GESTOR EMISSOR DT_VENC CD_PAIS PAIS CD_BV_MERC BV_MERC CD_ATIVO_BV_MERC RISCO_EMISSOR AG_RISCO DT_RISCO GRAU_RISCO DS_ATIVO_EXTERIOR QT_ATIVO_EXTERIOR VL_ATIVO_EXTERIOR",  # noqa: E501
    8: "DS_ATIVO PF_PJ_EMISSOR CPF_CNPJ_EMISSOR EMISSOR",
}
_POS_FIELDS = (
    _f("TP_FUNDO_CLASSE", "fund_type", "str", "fund type"),
    _f("CNPJ_FUNDO_CLASSE", "cnpj", "str", "fund (legacy) or class (CVM 175) CNPJ as written", required=True),
    _f("DT_COMPTC", "reference_date", "date", "competence date (month end)", required=True),
    _f("TP_APLIC", "position_category", "str", "category of the position (Acoes, Debentures, Cotas de Fundos...)"),
    _f("TP_ATIVO", "asset_type", "str", "type of the asset"),
    _f("EMISSOR_LIGADO", "related_issuer", "str", "issuer linked to the manager/administrator (S/N)"),
    _f("TP_NEGOC", "trading_intent", "str", "for trading / held to maturity"),
    _f("QT_VENDA_NEGOC", "sold_qty", "qty", "quantity sold in the month"),
    _f("VL_VENDA_NEGOC", "sold_brl", "brl", "value sold in the month"),
    _f("QT_AQUIS_NEGOC", "bought_qty", "qty", "quantity bought in the month"),
    _f("VL_AQUIS_NEGOC", "bought_brl", "brl", "value bought in the month"),
    _f("QT_POS_FINAL", "final_qty", "qty", "quantity held at month end"),
    _f("VL_MERC_POS_FINAL", "market_value_brl", "brl", "market value at month end"),
    _f("VL_CUSTO_POS_FINAL", "cost_value_brl", "brl", "cost value at month end"),
    _f("DT_CONFID_APLIC", "confidential_until", "date", "the position is confidential until this date"),
    _f("TP_TITPUB", "gov_bond_type", "str", "government bond name (LFT, LTN, NTN-B...)"),
    _f("CD_ISIN", "isin", "str", "ISIN"),
    _f("CD_SELIC", "selic_code", "str", "SELIC code of a government bond"),
    _f("DT_EMISSAO", "issued_on", "date", "issue date"),
    _f("DT_VENC", "maturity_date", "date", "maturity date"),
    _f("CNPJ_FUNDO_CLASSE_COTA", "held_fund_cnpj", "str", "CNPJ of the fund/class whose quotas are held"),
    _f("ID_SUBCLASSE", "held_subclass_id", "str", "subclass of the held fund"),
    _f("NM_FUNDO_CLASSE_SUBCLASSE_COTA", "held_fund_name", "str", "name of the held fund/class/subclass"),
    _f("CD_SWAP", "swap_code", "str", "swap code"),
    _f("DS_SWAP", "swap_description", "str", "swap description"),
    _f("CD_ATIVO", "asset_code", "str", "asset code (ticker for shares, code for debentures)"),
    _f("DS_ATIVO", "asset_description", "str", "asset description"),
    _f("DT_INI_VIGENCIA", "code_valid_from", "date", "start of validity of the code"),
    _f("DT_FIM_VIGENCIA", "code_valid_to", "date", "end of validity of the code"),
    _f(
        "CNPJ_EMISSOR",
        "issuer_tax_id",
        "str",
        "issuer CNPJ; blocks 6 and 8 call it CPF_CNPJ_EMISSOR; a natural person's CPF is never kept",
    ),
    _f("PF_PJ_EMISSOR", "issuer_person_type", "str", "issuer is a natural (PF) or legal (PJ) person"),
    _f("EMISSOR", "issuer_name", "str", "issuer name (null for a natural person)"),
    _f("TITULO_POSFX", "is_postfixed", "str", "post-fixed security (S/N)"),
    _f("CD_INDEXADOR_POSFX", "index_code", "str", "index code of a post-fixed security"),
    _f("DS_INDEXADOR_POSFX", "index_name", "str", "index name"),
    _f("PR_INDEXADOR_POSFX", "index_percent", "pct", "percentage of the index (post-fixed)", "% of index"),
    _f("PR_CUPOM_POSFX", "coupon_percent", "pct", "coupon (post-fixed)", "% a.a. as written"),
    _f("PR_TAXA_PREFX", "prefixed_rate_percent", "pct", "contracted rate (pre-fixed)", "% a.a. as written"),
    _f("RISCO_EMISSOR", "issuer_rated", "str", "issuer has a risk rating (S/N)"),
    _f("AG_RISCO", "rating_agency", "str", "rating agency"),
    _f("DT_RISCO", "rating_date", "date", "rating date"),
    _f("GRAU_RISCO", "rating", "str", "rating"),
    _f("TITULO_CETIP", "cetip_registered", "str", "registered at CETIP (S/N)"),
    _f("TITULO_GARANTIA", "has_guarantee", "str", "has a guarantee (S/N)"),
    _f("CNPJ_INSTITUICAO_FINANC_COOBR", "co_obligor_cnpj", "str", "co-obligor financial institution CNPJ"),
    _f("INVEST_COLETIVO", "collective_vehicle", "str", "collective investment vehicle (S/N)"),
    _f("INVEST_COLETIVO_GESTOR", "collective_vehicle_manager_influence", "str", "manager influences the vehicle (S/N)"),
    _f("CD_PAIS", "country_code", "str", "country code"),
    _f("PAIS", "country", "str", "country"),
    _f("CD_BV_MERC", "exchange_code", "str", "exchange or market code"),
    _f("BV_MERC", "exchange", "str", "exchange or market"),
    _f("CD_ATIVO_BV_MERC", "foreign_asset_code", "str", "code of the asset on the foreign market"),
    _f("DS_ATIVO_EXTERIOR", "foreign_asset_description", "str", "description of the foreign asset"),
    _f("QT_ATIVO_EXTERIOR", "foreign_qty", "qty", "quantity of the foreign asset"),
    _f(
        "VL_ATIVO_EXTERIOR",
        "foreign_value",
        "wide",
        "value of the foreign asset (float in the source; currency not stated)",
        "as written",
    ),
)
_POSITION_NAMES = [f.name for f in _POS_FIELDS]
POSITION_FIELDS = (
    _f(
        "BLC",
        "block",
        "i16",
        "CDA block: 1 public bonds, 2 fund quotas, 3 swaps, 4 equities and debentures, 5 bank credit, "
        "6 private credit, 7 abroad, 8 other",
        "",
        True,
    ),
    *_POS_FIELDS,
)
POSITION_TABLES = {
    n: Table(tuple(_BASE + cols.split()), frozenset({"ID_SUBCLASSE"}) if n == 2 else frozenset(), _POS_FIELDS, "")
    for n, cols in _BLOCKS.items()
}
POSITION = Table(
    (),
    frozenset(),
    POSITION_FIELDS,
    "Fund portfolio positions at month end (CDA blocks 1-8): what each fund holds.",
    (),
)
NET_ASSETS = Table(
    ["TP_FUNDO_CLASSE", "CNPJ_FUNDO_CLASSE", "DENOM_SOCIAL", "DT_COMPTC", "VL_PATRIM_LIQ"],
    frozenset(),
    (
        _f("TP_FUNDO_CLASSE", "fund_type", "str", "fund type"),
        _f("CNPJ_FUNDO_CLASSE", "cnpj", "str", "fund (legacy) or class (CVM 175) CNPJ as written", required=True),
        _f("DENOM_SOCIAL", "fund_name", "str", "registered name"),
        _f("DT_COMPTC", "reference_date", "date", "competence date (month end)", required=True),
        _f("VL_PATRIM_LIQ", "net_assets_brl", "brl", "net asset value at month end"),
    ),
    "Net assets of each fund at the CDA reference date.",
)
CDA_CONTRACTS = {
    "position": _contract("cvm_fi_cda", "position", POSITION, ()),
    "net_assets": _contract("cvm_fi_cda", "net_assets", NET_ASSETS),
}
_CPF = r"^\d{3}\.?\d{3}\.?\d{3}-?\d{2}$"


def parse_cda_position(data: bytes, name: str, block: int, row: dict[str, Any]) -> pl.DataFrame:
    """A BLC member as the union `position` frame. A natural person's CPF and name are dropped."""
    t = POSITION_TABLES[block]
    keep = tuple(
        Field("CPF_CNPJ_EMISSOR", f.name, f.kind, f.en, f.unit)
        if f.src == "CNPJ_EMISSOR" and "CPF_CNPJ_EMISSOR" in t.header
        else f
        for f in _POS_FIELDS
    )
    df = parse_csv(data, name, t, row, select=keep)
    natural = pl.col("issuer_tax_id").str.strip_chars().str.contains(_CPF).fill_null(False) | (
        pl.col("issuer_person_type") == "PF"
    ).fill_null(False)
    return df.with_columns(
        pl.when(natural).then(None).otherwise(pl.col("issuer_tax_id")).alias("issuer_tax_id"),
        pl.when(natural).then(None).otherwise(pl.col("issuer_name")).alias("issuer_name"),
        pl.lit(block, dtype=pl.Int16).alias("block"),
    ).select(["block", *_POSITION_NAMES, "raw_sha256", "raw_locator", "ingest_run_id"])


def parse_cda(blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
    for name, data in _members(blob, row):
        m = re.fullmatch(r"cda_fi_(?:BLC_([1-8])|(PL))_(\d{6}|\d{4})\.csv", name)
        if not m:
            continue  # cda_fiim, cda_fie, *CONFID*: not parsed (module docstring)
        if m.group(2):
            yield Parsed("net_assets", _period(m.group(3)), parse_csv(data, name, NET_ASSETS, row))
        else:
            yield Parsed("position", _period(m.group(3)), parse_cda_position(data, name, int(m.group(1)), row))


# ------------------------------------------------------------------------------------------------ connectors
def _months_back(today: date) -> Iterator[tuple[int, int]]:
    y, m = today.year, today.month
    while True:
        yield y, m
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)


class _CvmFundZips(Connector):
    """Zips of dados.cvm.gov.br/dados/<PATH>/ rewritten in place (docs/sources/cvm_fi_inf_diario.md §6): stored as
    members, staging keeps only changed rows (ADR-0014). Backfill takes every period once; the daily job asks
    conditionally (an unchanged file is a 304): the current and previous period daily, the trailing year weekly,
    older ones monthly. Periods never seen before are taken only by backfill."""

    version: ClassVar[str] = "1"
    dedup_staging: ClassVar[bool] = True
    min_interval: ClassVar[float] = 1.0  # CLAUDE.md: at most 1 request start per second per host
    concurrency: ClassVar[int] = 2
    PATH: ClassVar[str] = ""
    FETCH_DATASET: ClassVar[str] = ""  # dataset id of the fetched object in the manifest
    STEM: ClassVar[str] = ""  # file name stem before the period
    FIRST_MONTH: ClassVar[tuple[int, int] | None] = None  # first monthly zip (None: yearly zips only)
    HIST_YEARS: ClassVar[tuple[int, int] | None] = None  # frozen yearly archives below the monthly ones
    HIST_DEFAULT: ClassVar[bool] = False  # does backfill take them unless told otherwise (`hist=` option)
    RECENT_WEEKLY_MONTHS: ClassVar[int] = 13
    OLD_EVERY_DAYS: ClassVar[int] = 30

    def _spec(self, locator: str, url: str, ref: date) -> FetchSpec:
        return FetchSpec(
            self.source_id,
            self.FETCH_DATASET,
            url,
            "zip",
            reference_date=ref,
            absent_status=frozenset({404}),
            content_types=("application/zip", "application/x-zip-compressed"),
            locator=locator,
            unpack_members=True,
        )

    def catalogue(self, today: date, hist: bool) -> Iterator[tuple[str, str, date, int]]:
        """(locator, url, reference date, age in months or years-as-months) of every zip that can exist."""
        d = f"{BASE}/{self.PATH}/DADOS"
        if self.FIRST_MONTH is not None:
            for y, m in _months_back(today):
                if (y, m) < self.FIRST_MONTH:
                    break
                age = (today.year - y) * 12 + today.month - m
                yield f"{y}{m:02d}", f"{d}/{self.STEM}_{y}{m:02d}.zip", date(y, m, 1), age
        if hist and self.HIST_YEARS is not None:
            for y in range(self.HIST_YEARS[0], self.HIST_YEARS[1] + 1):
                yield f"hist{y}", f"{d}/HIST/{self.STEM}_{y}.zip", date(y, 12, 31), 10_000

    def discover(self, mode: Mode, zones: Zones, **options: Any) -> Iterable[FetchSpec]:
        today = today_brt()
        hist = bool(options.get("hist", self.HIST_DEFAULT))
        wanted = {str(p) for p in options.get("periods") or ()}
        held = held_rows(zones, self.source_id, self.FETCH_DATASET)
        last: dict[str, date] = {}
        if held.height:
            for note, at in zip(held["notes"].to_list(), held["fetched_at"].to_list(), strict=True):
                if note is not None and "|" not in note:
                    last[note] = max(last.get(note, at.date()), at.date())
        for locator, url, ref, age in self.catalogue(today, hist):
            if wanted and locator not in wanted:
                continue
            seen = last.get(locator)
            if mode is Mode.BACKFILL:
                if seen is None:
                    yield self._spec(locator, url, ref)
            elif age < 10_000 and seen is not None:
                every = 1 if age <= 1 else (7 if age <= self.RECENT_WEEKLY_MONTHS else self.OLD_EVERY_DAYS)
                if (today - seen).days >= every:
                    yield self._spec(locator, url, ref)
            elif age < 10_000 and seen is None and age <= self.RECENT_WEEKLY_MONTHS:
                yield self._spec(locator, url, ref)  # a period that appeared since the last run


class CvmFii(_CvmFundZips):
    """FII monthly, quarterly and annual reports (yearly zips), `parse_fii`. FIAGRO has other layouts: not parsed."""

    source_id: ClassVar[str] = "cvm_fii"
    contracts: ClassVar[dict[str, Contract]] = FII_CONTRACTS
    FETCH_DATASET: ClassVar[str] = "inf_fii"

    def catalogue(self, today: date, hist: bool) -> Iterator[tuple[str, str, date, int]]:
        for kind, stem in (
            ("INF_MENSAL", "inf_mensal_fii"),
            ("INF_TRIMESTRAL", "inf_trimestral_fii"),
            ("INF_ANUAL", "inf_anual_fii"),
        ):
            for y in range(2016, today.year + 1):
                url = f"{BASE}/FII/DOC/{kind}/DADOS/{stem}_{y}.zip"
                yield f"{kind.lower()}-{y}", url, date(y, 12, 31), 2 if y >= today.year - 1 else 24  # weekly / monthly

    def parse(self, blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
        return parse_fii(blob, row)


class CvmFiInfDiario(_CvmFundZips):
    """Daily NAV per fund: monthly zips 2021-01-, yearly HIST zips (monthly members) 2000-2020."""

    source_id: ClassVar[str] = "cvm_fi_inf_diario"
    contracts: ClassVar[dict[str, Contract]] = DAILY_CONTRACTS
    PATH: ClassVar[str] = "FI/DOC/INF_DIARIO"
    FETCH_DATASET: ClassVar[str] = "inf_diario"
    STEM: ClassVar[str] = "inf_diario_fi"
    FIRST_MONTH: ClassVar[tuple[int, int] | None] = (2021, 1)
    HIST_YEARS: ClassVar[tuple[int, int] | None] = (2000, 2020)
    HIST_DEFAULT: ClassVar[bool] = True
    concurrency: ClassVar[int] = 3

    def parse(self, blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
        return parse_inf_diario(blob, row)


class CvmFiCda(_CvmFundZips):
    """Fund portfolios: monthly zips 2023-01-. The 2005-2022 yearly archives (1.2 GB zipped, members up to 640 MB
    unzipped) are taken only with the option `hist=True`."""

    source_id: ClassVar[str] = "cvm_fi_cda"
    contracts: ClassVar[dict[str, Contract]] = CDA_CONTRACTS
    PATH: ClassVar[str] = "FI/DOC/CDA"
    FETCH_DATASET: ClassVar[str] = "cda"
    STEM: ClassVar[str] = "cda_fi"
    FIRST_MONTH: ClassVar[tuple[int, int] | None] = (2023, 1)
    HIST_YEARS: ClassVar[tuple[int, int] | None] = (2005, 2022)
    HIST_DEFAULT: ClassVar[bool] = False
    RECENT_WEEKLY_MONTHS: ClassVar[int] = 4  # a month fills over ~3 months (docs/sources/cvm_fi_cda.md)
    concurrency: ClassVar[int] = 3

    def parse(self, blob: bytes, row: dict[str, Any]) -> Iterable[Parsed]:
        return parse_cda(blob, row)
