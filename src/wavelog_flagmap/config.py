"""YAML configuration with ${ENV_VAR} expansion (so API keys stay out of files)."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class Config:
    # data source: wavelog, lotw, clublog, qrz, wrl or adif; None = the first one configured, in the order
    # adif, wavelog, lotw, clublog, qrz, wrl
    source: str | None = None
    adif: str | None = None          # ADIF file path or http(s) URL
    lotw_username: str | None = None
    lotw_password: str | None = None
    lotw_owncall: str | None = None  # only QSOs made as this callsign (default: all of the account's)
    clublog_token: str | None = None
    clublog_callsign: str | None = None  # default: callsign
    qrz_key: str | None = None       # QRZ Logbook API access key (needs a QRZ subscription)
    wrl_key: str | None = None       # World Radio League API key (wrl_live_...)
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
        v = os.path.expandvars(v)
        return "" if re.search(r"\$\{\w+\}", v) else v  # unset ${VAR}: empty, not the literal text
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
    src = raw.get("source", {}) or {}
    lotw = raw.get("lotw", {}) or {}
    cfg = Config(
        source=src.get("type"),
        adif=src.get("adif"),
        lotw_username=lotw.get("username") or os.environ.get("LOTW_USERNAME"),
        lotw_password=lotw.get("password") or os.environ.get("LOTW_PASSWORD"),
        lotw_owncall=lotw.get("owncall"),
        clublog_token=(raw.get("clublog") or {}).get("token") or os.environ.get("CLUBLOG_TOKEN"),
        clublog_callsign=(raw.get("clublog") or {}).get("callsign") or os.environ.get("CLUBLOG_CALLSIGN"),
        qrz_key=(raw.get("qrz") or {}).get("key") or os.environ.get("QRZ_LOGBOOK_KEY"),
        wrl_key=(raw.get("wrl") or {}).get("key") or os.environ.get("WRL_API_KEY"),
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
