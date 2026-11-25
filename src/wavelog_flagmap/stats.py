"""Turn QSO records into per-DXCC-entity counts."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from . import data

METRICS = ("qsos", "confirmed")


@dataclass
class EntityCount:
    entity: data.Entity
    qsos: int = 0
    confirmed: int = 0

    def value(self, metric: str) -> int:
        return self.confirmed if metric == "confirmed" else self.qsos


def _confirmed(rec: dict[str, str]) -> bool:
    """LoTW, paper/direct QSL and eQSL confirmations all count."""
    return any(rec.get(k, "").upper() == "Y"
               for k in ("lotw_qsl_rcvd", "qsl_rcvd", "eqsl_qsl_rcvd"))


def count_entities(qsos: Iterable[dict[str, str]]) -> tuple[dict[int, EntityCount], int]:
    """Return ({dxcc: EntityCount}, skipped) where skipped = records with no resolvable entity."""
    ents = data.entities()
    out: dict[int, EntityCount] = {}
    skipped = 0
    for rec in qsos:
        entity = None
        raw = rec.get("dxcc", "")
        if raw.isdigit() and int(raw) in ents:
            entity = ents[int(raw)]
        elif rec.get("country"):
            entity = data.entity_by_name(rec["country"])
        if entity is None:
            skipped += 1
            continue
        ec = out.setdefault(entity.dxcc, EntityCount(entity))
        ec.qsos += 1
        if _confirmed(rec):
            ec.confirmed += 1
    return out, skipped


def ranked(counts: dict[int, EntityCount], metric: str = "qsos") -> list[EntityCount]:
    """Entities with a non-zero value for `metric`, biggest first (ties by name)."""
    if metric not in METRICS:
        raise ValueError(f"metric must be one of {METRICS}")
    rows = [c for c in counts.values() if c.value(metric) > 0]
    rows.sort(key=lambda c: (-c.value(metric), c.entity.name))
    return rows
