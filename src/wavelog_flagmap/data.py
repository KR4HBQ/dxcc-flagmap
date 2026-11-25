"""Bundled reference data: DXCC entities, land polygons, flag images."""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"


@dataclass(frozen=True)
class Entity:
    dxcc: int
    name: str
    iso: str  # flag-icons code, lower case ("us", "gb-sct"); may be "" / "zz" (no flag)
    lat: float
    lon: float
    continent: str
    prefix: str


@lru_cache(maxsize=1)
def entities() -> dict[int, Entity]:
    rows = json.loads((DATA_DIR / "dxcc_entities.json").read_text())
    return {r["dxcc"]: Entity(**r) for r in rows}


@lru_cache(maxsize=1)
def _names() -> dict[str, int]:
    return {_norm(e.name): e.dxcc for e in entities().values()}


def _norm(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


def entity_by_name(name: str) -> Entity | None:
    """Best-effort lookup by country name (fallback when a QSO has no DXCC number)."""
    code = _names().get(_norm(name))
    return entities().get(code) if code else None


@lru_cache(maxsize=1)
def land_polygons() -> list[list[list[float]]]:
    return json.loads((DATA_DIR / "land.json").read_text())


def flag_path(iso: str) -> Path | None:
    p = DATA_DIR / "flags" / f"{iso}.png"
    return p if iso and p.exists() else None
