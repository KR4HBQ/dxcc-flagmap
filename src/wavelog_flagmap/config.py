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
    station_id: str | None = None

    callsign: str = ""
    metric: str = "qsos"             # "qsos" | "confirmed"
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


def load(path: str | Path | None) -> Config:
    raw: dict[str, Any] = {}
    if path:
        raw = _expand(yaml.safe_load(Path(path).read_text()) or {})
    wl = raw.get("wavelog", {}) or {}
    cfg = Config(
        adif=(raw.get("source", {}) or {}).get("adif"),
        wavelog_url=wl.get("url"),
        wavelog_api=str(wl.get("api", "v1")),
        wavelog_key=wl.get("key") or os.environ.get("WAVELOG_API_KEY"),
        station_id=str(wl["station_id"]) if wl.get("station_id") is not None else None,
        callsign=raw.get("callsign", ""),
        metric=raw.get("metric", "qsos"),
        theme=raw.get("theme", "light"),
        output_dir=raw.get("output_dir", "./out"),
        grid=raw.get("grid", {}) or {},
        map=raw.get("map", {}) or {},
    )
    return cfg
