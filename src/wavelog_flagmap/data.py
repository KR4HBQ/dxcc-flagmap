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


@lru_cache(maxsize=1)
def _prefixes() -> tuple[dict[str, int], dict[str, int], int]:
    t = json.loads((DATA_DIR / "prefixes.json").read_text(encoding="utf-8"))
    return t["p"], t["c"], max(map(len, t["p"]), default=1)


# Portable suffixes that never change the entity ("/MM" and "/AM" mean no DXCC entity at all).
_SUFFIXES = {"P", "M", "QRP", "A", "R", "LH", "J", "B", "QRPP", "LGT", "PM", "T", "X"}


def entity_by_call(call: str) -> Entity | None:
    """DXCC entity for a callsign from cty.dat prefixes (fallback when a QSO has no DXCC field).

    Handles exact-call overrides (e.g. special event and island stations) and prefixed or
    suffixed portable calls such as KH6/W1AW, W1AW/KH6 and DL1ABC/P. /MM and /AM return None.
    """
    prefixes, calls, longest = _prefixes()
    call = call.strip().upper()
    if not call:
        return None
    code = calls.get(call)
    if code is None:
        parts = [p for p in call.split("/") if p]
        if any(p in ("MM", "AM") for p in parts[1:]):
            return None
        parts = [p for i, p in enumerate(parts) if i == 0 or (p not in _SUFFIXES and not p.isdigit())]
        if not parts:
            return None
        if len(parts) == 1:
            base = parts[0]
        else:  # the shorter part is the operating prefix: KH6/W1AW, W1AW/KH6, EA8/DL1ABC
            base = min(parts[:2], key=len)
        code = calls.get(base)
        if code is None:
            for n in range(min(len(base), longest), 0, -1):
                code = prefixes.get(base[:n])
                if code is not None:
                    break
        # Guantanamo Bay is only ever KG4 + two letters; other KG4 calls are ordinary US calls
        if code == 105 and base.startswith("KG4") and len(base) != 5:
            code = 291
    return entities().get(code) if code is not None else None
