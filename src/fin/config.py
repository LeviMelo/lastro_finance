"""Where the zones live (PLAN §4.2).

The data home defaults to `<repo>/data` and is overridden by the `FIN_DATA_HOME` environment variable (tests use a
temporary home). Nothing else derives a path from the working directory.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Zones:
    """The data home and its zones. `raw` and `manifest` are L1 and immutable; everything else is rebuildable."""

    home: Path

    @property
    def raw(self) -> Path:
        return self.home / "raw"

    @property
    def manifest(self) -> Path:
        return self.home / "manifest"

    @property
    def runs(self) -> Path:
        return self.home / "runs"

    @property
    def logs(self) -> Path:
        return self.home / "logs"

    @property
    def staging(self) -> Path:
        return self.home / "staging"

    @property
    def core(self) -> Path:
        return self.home / "core"

    @property
    def derived(self) -> Path:
        return self.home / "derived"

    @property
    def quarantine(self) -> Path:
        return self.home / "quarantine"

    @property
    def exports(self) -> Path:
        return self.home / "exports"

    @property
    def catalog(self) -> Path:
        return self.home / "catalog.duckdb"

    def rebuildable(self) -> tuple[Path, ...]:
        """The zones a full rebuild replaces (PLAN §4.1 invariant 10)."""
        return (self.staging, self.core, self.derived, self.quarantine)


def zones() -> Zones:
    home = os.environ.get("FIN_DATA_HOME")
    return Zones(Path(home) if home else REPO_ROOT / "data")
