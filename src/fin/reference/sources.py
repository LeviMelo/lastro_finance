"""The source registry, loaded from `sources.toml` and validated (PLAN §4.3.1)."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Literal

Tier = Literal["P", "S", "U"]
Status = Literal["recon", "archiving", "parsed"]
_TIERS = {"P", "S", "U"}
_STATUS = {"recon", "archiving", "parsed"}


@dataclass(frozen=True)
class Source:
    source_id: str
    name: str
    institution: str
    access: str
    tier: Tier
    ephemeral: bool
    status: Status
    recon: str

    @property
    def official(self) -> bool:
        return self.tier == "P"


@cache
def registry() -> dict[str, Source]:
    raw = tomllib.loads((Path(__file__).with_name("sources.toml")).read_text(encoding="utf-8"))
    out: dict[str, Source] = {}
    for sid, e in raw.items():
        if e["tier"] not in _TIERS or e["status"] not in _STATUS:
            raise ValueError(f"sources.toml [{sid}]: bad tier or status")
        out[sid] = Source(
            sid, e["name"], e["institution"], e["access"], e["tier"], bool(e["ephemeral"]), e["status"], e["recon"]
        )
    return out
