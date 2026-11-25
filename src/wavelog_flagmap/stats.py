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


# confirmation source -> ADIF field that is "Y" when the QSO is confirmed there
CONFIRM_FIELDS = {
    "lotw": "lotw_qsl_rcvd",
    "qsl": "qsl_rcvd",            # paper / direct / bureau card
    "eqsl": "eqsl_qsl_rcvd",
    "qrz": "qrzcom_qso_download_status",
    "clublog": "clublog_qso_download_status",
    "dcl": "dcl_qsl_rcvd",
}
# ARRL DXCC accepts LoTW and QSL cards; this is also Wavelog's default on its DXCC award page.
DEFAULT_CONFIRM = ("lotw", "qsl")


def _confirmed(rec: dict[str, str], fields: tuple[str, ...]) -> bool:
    return any(rec.get(f, "").upper() == "Y" for f in fields)


def confirm_fields(sources: Iterable[str]) -> tuple[str, ...]:
    out = []
    for s in sources:
        key = s.strip().lower()
        if key not in CONFIRM_FIELDS:
            raise ValueError(f"unknown confirmation source {s!r}; use {', '.join(CONFIRM_FIELDS)}")
        out.append(CONFIRM_FIELDS[key])
    return tuple(out)


def count_entities(qsos: Iterable[dict[str, str]], confirmed_by: Iterable[str] = DEFAULT_CONFIRM,
                   ) -> tuple[dict[int, EntityCount], int]:
    """Return ({dxcc: EntityCount}, skipped) where skipped = records with no resolvable entity."""
    fields = confirm_fields(confirmed_by)
    ents = data.entities()
    out: dict[int, EntityCount] = {}
    skipped = 0
    for rec in qsos:
        entity = None
        raw = rec.get("dxcc", "").strip()
        if raw:  # an explicit DXCC field wins; 0 means "no entity" (e.g. /MM)
            entity = ents.get(int(raw)) if raw.isdigit() else None
        else:  # loggers that omit DXCC: callsign prefix (cty.dat), then country name
            if rec.get("call"):
                entity = data.entity_by_call(rec["call"])
            if entity is None and rec.get("country"):
                entity = data.entity_by_name(rec["country"])
        if entity is None:
            skipped += 1
            continue
        ec = out.setdefault(entity.dxcc, EntityCount(entity))
        ec.qsos += 1
        if _confirmed(rec, fields):
            ec.confirmed += 1
    return out, skipped


def summary(counts: dict[int, EntityCount], *, confirmations: bool = True) -> str:
    """Footer line, e.g. '124 worked / 96 confirmed / 5,210 QSOs'.

    ``confirmations=False`` for sources that carry no QSL status (the count would always be 0).
    """
    worked = len(counts)
    confirmed = sum(1 for c in counts.values() if c.confirmed)
    qsos = sum(c.qsos for c in counts.values())
    if not confirmations:
        return f"{worked} worked / {qsos:,} QSOs"
    return f"{worked} worked / {confirmed} confirmed / {qsos:,} QSOs"


def ranked(counts: dict[int, EntityCount], metric: str = "qsos") -> list[EntityCount]:
    """Entities with a non-zero value for `metric`, biggest first (ties by name)."""
    if metric not in METRICS:
        raise ValueError(f"metric must be one of {METRICS}")
    rows = [c for c in counts.values() if c.value(metric) > 0]
    rows.sort(key=lambda c: (-c.value(metric), c.entity.name))
    return rows
