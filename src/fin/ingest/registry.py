"""Which connector implements which registered source, and which run in the daily job."""

from __future__ import annotations

from fin.ingest.alternates import (
    BcbSgs,
    CvmDfpItr,
    CvmFca,
    CvmFre,
    CvmIpe,
    FundosNetRendimentos,
    Ipeadata,
    PyieldData,
    SndDebentures,
    TesouroVna,
    YahooChart,
)
from fin.ingest.anbima_calendar import AnbimaCalendar
from fin.ingest.b3_cotahist import B3Cotahist
from fin.ingest.base import Connector
from fin.ingest.context import context_connectors
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
    TesouroPrecoTaxa,
)
from fin.reference.sources import registry

CONNECTORS: dict[str, type[Connector]] = {
    c.source_id: c
    for c in (
        AnbimaCalendar,
        AnbimaTitulosPublicos,
        AnbimaEttj,
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
        CvmDfpItr,
        CvmFca,
        CvmFre,
        CvmIpe,
        FundosNetRendimentos,
        Ipeadata,
        PyieldData,
        SndDebentures,
        TesouroVna,
        YahooChart,
        *context_connectors(),
    )
}

# The calendar first: the windowed snapshots compute their dates from it.
DAILY: tuple[str, ...] = (
    "anbima_calendar",
    "anbima_titulos_publicos",
    "anbima_ettj",
    "anbima_vna",
    "anbima_debentures",
    "anbima_projecoes",
    "b3_bdi",
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
    "bcb_sgs",
    "ipeadata",
    "tesouro_vna",
    # CVM keeps only the latest version of each filing: weekly/monthly versions keep restatements (cadence inside)
    "cvm_dfp_itr",
    "cvm_fca",
    "cvm_fre",
    "cvm_ipe",
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
