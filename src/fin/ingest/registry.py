"""Which connector implements which registered source, and which run in the daily job."""

from __future__ import annotations

from fin.ingest.alternates import (
    BcbSgs,
    CvmDfpItr,
    CvmFca,
    CvmFre,
    CvmIpe,
    CvmVlmo,
    FundosNetCda,
    FundosNetInformeDiario,
    FundosNetRendimentos,
    IbgeSidra,
    Ipeadata,
    PyieldData,
    SndDebentures,
    TesouroVna,
    YahooChart,
)
from fin.ingest.anbima_calendar import AnbimaCalendar
from fin.ingest.b3_cotahist import B3Cotahist
from fin.ingest.b3_events import B3CompanyEvents
from fin.ingest.b3_fixed_income import B3FixedIncome
from fin.ingest.b3_funds_listed import B3FundsListed
from fin.ingest.b3_holidays import B3Holidays
from fin.ingest.base import Connector
from fin.ingest.binance import BinanceKlines
from fin.ingest.context import context_connectors
from fin.ingest.cvm_funds import CvmFiCda, CvmFii, CvmFiInfDiario
from fin.ingest.cvm_rad import CvmRadVersions
from fin.ingest.intraday import YahooIntraday
from fin.ingest.ptax import BcbPtax
from fin.ingest.snapshots import (
    AnbimaDebentures,
    AnbimaEttj,
    AnbimaIndicadores,
    AnbimaTitulosPublicos,
    AnbimaVna,
    B3Bdi,
    B3Files,
    B3IndexLevels,
    B3IndexPortfolio,
    B3PesquisaPregao,
    CvmCiaCadastro,
    CvmFiCadastro,
    NefinFactors,
    SusepEttj,
    TesouroPrecoTaxa,
)
from fin.ingest.snd_pu import SndPuHistorico
from fin.ingest.tiingo import TiingoDaily
from fin.reference.sources import registry

CONNECTORS: dict[str, type[Connector]] = {
    c.source_id: c
    for c in (
        AnbimaCalendar,
        AnbimaTitulosPublicos,
        AnbimaEttj,
        SusepEttj,
        AnbimaVna,
        AnbimaDebentures,
        AnbimaIndicadores,
        B3Bdi,
        B3Files,
        B3IndexLevels,
        B3IndexPortfolio,
        B3PesquisaPregao,
        B3Cotahist,
        CvmCiaCadastro,
        CvmFiCadastro,
        TesouroPrecoTaxa,
        NefinFactors,
        BcbSgs,
        BcbPtax,
        CvmDfpItr,
        CvmFca,
        CvmFre,
        CvmIpe,
        CvmVlmo,
        CvmFii,
        CvmFiInfDiario,
        CvmFiCda,
        CvmRadVersions,
        FundosNetCda,
        FundosNetInformeDiario,
        FundosNetRendimentos,
        IbgeSidra,
        Ipeadata,
        PyieldData,
        SndDebentures,
        TesouroVna,
        YahooChart,
        YahooIntraday,
        B3CompanyEvents,
        B3FixedIncome,
        B3Holidays,
        B3FundsListed,
        BinanceKlines,
        TiingoDaily,
        SndPuHistorico,
        *context_connectors(),
    )
}

# The calendar first: the windowed snapshots compute their dates from it.
DAILY: tuple[str, ...] = (
    "b3_holidays",  # before the calendar: B3's published closures extend is_b3_trading_day (OQ-1)
    "anbima_calendar",
    "anbima_titulos_publicos",
    "anbima_ettj",
    "susep_ettj",  # month-end copies of ANBIMA's ETTJ since 2015-12 (the last 3 months asked daily)
    "anbima_vna",
    "anbima_debentures",
    "anbima_projecoes",
    "b3_bdi",
    "b3_fixed_income",  # B3 OTC fixed-income trades (drp.b3.com.br): back to 2023-03 only while served
    "b3_instruments",
    "b3_index_portfolio",
    "b3_index_levels",
    "b3_pesquisapregao",
    "cvm_cia_cadastro",
    "cvm_fi_cadastro",
    "b3_cotahist",  # not ephemeral (daily files back to 2014): keeps prices current
    "tesouro_transparente",  # replaced in full daily: each replacement is a version (304 when unchanged)
    "nefin",
    # gap-closing routes (docs/evaluation/2026-11-07-data-gap-matrix.md); pyield_data and yahoo_chart run on demand
    "snd_debentures",  # terms snapshot daily, agenda weekly: neither keeps history
    "b3_fundosnet",
    "b3_fundosnet_daily",  # ETF daily NAV (not in CVM open data since 2018-09)
    "b3_fundosnet_cda",  # ETF monthly portfolios (not in CVM open data)
    "tiingo",  # US benchmarks and ADRs, the last 10 days (owner token; nothing runs without it)
    "binance",  # crypto daily klines: new monthly files and this month's days (scope priority 3)
    "b3_funds_listed",  # B3's listed funds today (current state only) and each ETF's report ids
    "bcb_sgs",
    "bcb_ptax",
    "ipeadata",
    "ibge_sidra",
    "tesouro_vna",
    # CVM keeps only the latest version of each filing: weekly/monthly versions keep restatements (cadence inside)
    "cvm_dfp_itr",
    "cvm_fca",
    "cvm_fre",
    "cvm_ipe",
    "cvm_vlmo",
    "cvm_fii",
    "cvm_fi_inf_diario",
    "cvm_fi_cda",
    "cvm_rad_versions",  # superseded DFP/ITR versions, kept as statements only (ADR-0027)
    "yahoo_intraday",  # tier U: 5-minute bars exist only ~60 days back, so they are archived as they pass
    "b3_company_events",  # each issuer weekly: the Supplement is current state only
    # the context catalogue (reference/context_series.toml): each entry carries its own cadence
    *(c.source_id for c in context_connectors()),
)


def connector(source_id: str) -> Connector:
    if source_id not in registry():
        raise KeyError(f"{source_id} is not in the source registry (src/fin/reference/sources.toml)")
    if source_id not in CONNECTORS:
        raise KeyError(f"{source_id} has no connector yet (status: {registry()[source_id].status})")
    return CONNECTORS[source_id]()


def missing_ephemeral() -> list[str]:
    """Ephemeral sources with no daily archiving: every day they stay here is a day lost."""
    return [s for s, src in registry().items() if src.ephemeral and s not in DAILY]
