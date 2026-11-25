"""YAML configuration with ${ENV_VAR} expansion (so API keys stay out of files)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class Config:
    # data source: either a local ADIF file or a Wavelog instance
    adif: str | None = None
    wavelog_url: str | None = None
    wavelog_api: str = "v1"          # "v1" (api key) or "v2" (bearer token)
    wavelog_key: str | None = None
    station_ids: list[str] = field(default_factory=list)  # one or more Station Location ids

    callsign: str = ""
    metric: str = "qsos"             # "qsos" | "confirmed"
    confirmed_by: list[str] = field(default_factory=lambda: ["lotw", "qsl"])
    theme: str = "light"             # "light" | "dark"
    output_dir: str = "./out"
    grid: dict[str, Any] = field(default_factory=dict)
    map: dict[str, Any] = field(default_factory=dict)


def _expand(v: Any) -> Any:
    if isinstance(v, str):
        return os.path.expandvars(v)
    if isinstance(v, dict):
        return {k: _expand(x) for k, x in v.items()}
    return v


def _list(v: Any) -> list[str]:
    if v is None:
        return []
    items = v if isinstance(v, (list, tuple)) else str(v).split(",")
    return [str(x).strip().lower() for x in items if str(x).strip()]


def parse_station_ids(v: Any) -> list[str]:
    """Accept 3, "3", "1,2,5", "1-12", "1-4, 7" or a YAML list of those.

    An empty list (``all``, or no value) means every station location of the API key's user.
    """
    if v is None or v == "" or str(v).strip().lower() == "all":
        return []
    items = v if isinstance(v, (list, tuple)) else str(v).split(",")
    out: list[str] = []
    for item in items:
        s = str(item).strip()
        if not s:
            continue
        if "-" in s:
            lo, hi = (int(x) for x in s.split("-", 1))
            out.extend(str(i) for i in range(lo, hi + 1))
        else:
            out.append(str(int(s)))
    return list(dict.fromkeys(out))


def load(path: str | Path | None) -> Config:
    raw: dict[str, Any] = {}
    if path:
        raw = _expand(yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {})
    wl = raw.get("wavelog", {}) or {}
    cfg = Config(
        adif=(raw.get("source", {}) or {}).get("adif"),
        wavelog_url=wl.get("url"),
        wavelog_api=str(wl.get("api", "v1")),
        wavelog_key=wl.get("key") or os.environ.get("WAVELOG_API_KEY"),
        station_ids=parse_station_ids(wl.get("station_id")),
        callsign=raw.get("callsign", ""),
        metric=raw.get("metric", "qsos"),
        confirmed_by=_list(raw.get("confirmed_by")) or ["lotw", "qsl"],
        theme=raw.get("theme", "light"),
        output_dir=raw.get("output_dir", "./out"),
        grid=raw.get("grid", {}) or {},
        map=raw.get("map", {}) or {},
    )
    return cfg
