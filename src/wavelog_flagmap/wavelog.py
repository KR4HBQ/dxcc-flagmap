"""Fetch QSOs from a Wavelog instance as ADIF.

Two API generations are supported:

* ``v1`` - ``POST /index.php/api/get_contacts_adif`` with a read-only API key
  and a station profile id (paged with ``fetchfromid``). Works on every
  Wavelog release.
* ``v2`` - ``GET /index.php/api/v2/qso?format=adif`` with a ``wl2_...`` bearer
  token (paged with ``since_id``). Newer releases only.

See https://docs.wavelog.org/ for the API reference.
"""
from __future__ import annotations

from typing import Iterator

import requests

TIMEOUT = 60


class WavelogError(RuntimeError):
    pass


def _base(url: str) -> str:
    return url.rstrip("/")


def fetch_v1(url: str, key: str, station_id: int | str, *, max_pages: int = 1000) -> Iterator[str]:
    """Yield ADIF text chunks until the instance reports nothing new."""
    endpoint = f"{_base(url)}/index.php/api/get_contacts_adif"
    last_id = 0
    for _ in range(max_pages):
        resp = requests.post(endpoint, json={"key": key, "station_id": str(station_id),
                                             "fetchfromid": last_id}, timeout=TIMEOUT)
        if resp.status_code != 200:
            raise WavelogError(f"Wavelog answered HTTP {resp.status_code} from {endpoint}")
        try:
            body = resp.json()
        except ValueError as exc:
            raise WavelogError("Wavelog did not return JSON - check the URL, API key and station_id") from exc
        adif = body.get("adif") or ""
        new_last = int(body.get("lastfetchedid") or last_id)
        if adif.strip():
            yield adif
        if new_last <= last_id or not adif.strip():
            return
        last_id = new_last


def fetch_v2(url: str, token: str, station_id: int | str | None = None, *,
             per_page: int = 1000, max_pages: int = 1000) -> Iterator[str]:
    """Yield ADIF text chunks using the v2 API (bearer token)."""
    endpoint = f"{_base(url)}/index.php/api/v2/qso"
    headers = {"Authorization": f"Bearer {token}"}
    since_id = 0
    for _ in range(max_pages):
        params = {"format": "adif", "since_id": since_id, "per_page": per_page}
        if station_id not in (None, ""):
            params["station_id"] = station_id
        resp = requests.get(endpoint, params=params, headers=headers, timeout=TIMEOUT)
        if resp.status_code != 200:
            raise WavelogError(f"Wavelog answered HTTP {resp.status_code} from {endpoint}")
        text = resp.text
        if not text.strip():
            return
        yield text
        # v2 paging: continue after the highest QSO id; header names may vary by release
        nxt = resp.headers.get("X-Last-Id") or resp.headers.get("X-Next-Since-Id")
        if not nxt or int(nxt) <= since_id:
            return
        since_id = int(nxt)
