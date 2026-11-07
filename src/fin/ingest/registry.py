"""Which connector implements which registered source, and which run in the daily job."""

from __future__ import annotations

from fin.ingest.anbima_calendar import AnbimaCalendar
from fin.ingest.base import Connector
from fin.ingest.snapshots import AnbimaTitulosPublicos, B3Bdi, CvmCiaCadastro, CvmFiCadastro
from fin.reference.sources import registry

CONNECTORS: dict[str, type[Connector]] = {
    c.source_id: c for c in (AnbimaCalendar, AnbimaTitulosPublicos, B3Bdi, CvmCiaCadastro, CvmFiCadastro)
}

# The calendar first: the windowed snapshots compute their dates from it.
DAILY: tuple[str, ...] = ("anbima_calendar", "anbima_titulos_publicos", "b3_bdi", "cvm_cia_cadastro", "cvm_fi_cadastro")


def connector(source_id: str) -> Connector:
    if source_id not in registry():
        raise KeyError(f"{source_id} is not in the source registry (src/fin/reference/sources.toml)")
    if source_id not in CONNECTORS:
        raise KeyError(f"{source_id} has no connector yet (status: {registry()[source_id].status})")
    return CONNECTORS[source_id]()


def missing_ephemeral() -> list[str]:
    """Ephemeral sources with no daily archiving: every day they stay here is a day lost."""
    return [s for s, src in registry().items() if src.ephemeral and s not in DAILY]
