from __future__ import annotations

from pathlib import Path

import pytest

from fin.config import Zones

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def zones(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Zones:
    monkeypatch.setenv("FIN_DATA_HOME", str(tmp_path / "home"))
    return Zones(tmp_path / "home")
