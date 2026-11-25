"""Fetch QSOs from a Wavelog instance as ADIF.

Two API generations are supported:

* ``v1`` - ``POST /index.php/api/get_contacts_adif`` with a read-only API key
  and a station location id. JSON body ``{key, station_id, fetchfromid}``;
  response ``{status, message, lastfetchedid, exported_qsos, adif}`` where
  ``adif`` is ``null`` when nothing new is available. Wavelog returns at most
  ``limit`` (default 20000) QSOs per call, so we page with ``fetchfromid``.
  Works on every Wavelog release.
* ``v2`` - ``GET /index.php/api/v2/qso?format=adif`` with a ``wl2_...`` bearer
  token (Wavelog >= 3.1.0, scope ``qso:read``). Response envelope
  ``{"data": {"exported", "lastfetchedid", "adif"}, "meta": {..., "has_more"}}``;
  rows are ascending by id, so we page by feeding ``lastfetchedid`` back as
  ``since_id``. Implemented from docs.wavelog.org/developer/api-v2/qso/ and not
  yet verified against a live instance - treat as experimental.
"""
from __future__ import annotations

from typing import Iterator

import requests

TIMEOUT = 60


class WavelogError(RuntimeError):
    pass


def _base(url: str) -> str:
    return url.rstrip("/")


def _json(resp: requests.Response, endpoint: str) -> dict:
    try:
        body = resp.json()
    except ValueError:
        body = None
    if resp.status_code != 200 or not isinstance(body, dict):
        reason = ""
        if isinstance(body, dict):
            err = body.get("error")
            if isinstance(err, dict):  # v2 error envelope
                reason = f"{err.get('code', '')}: {err.get('message', '')}".strip(": ")
            else:  # v1: {"status": "failed", "reason": ...}
                reason = str(body.get("reason") or body.get("message") or "")
        if resp.status_code == 200:
            raise WavelogError(f"Wavelog did not return JSON from {endpoint} - check the URL")
        raise WavelogError(f"Wavelog answered HTTP {resp.status_code} from {endpoint}"
                           + (f" ({reason})" if reason else ""))
    return body


def station_ids_v1(url: str, key: str) -> list[str]:
    """All station location ids visible to the key (``GET /index.php/api/station_info/{key}``).

    Wavelog returns every location of the key's user, or only those linked to the active
    logbook when the user enabled "active logbook only" in their station settings.
    """
    endpoint = f"{_base(url)}/index.php/api/station_info/"
    resp = requests.get(endpoint + requests.utils.quote(key, safe=""), timeout=TIMEOUT)
    try:
        body = resp.json()
    except ValueError:
        body = None
    if resp.status_code != 200 or not isinstance(body, list):
        reason = body.get("reason", "") if isinstance(body, dict) else ""
        raise WavelogError(f"Wavelog answered HTTP {resp.status_code} from {endpoint}"
                           + (f" ({reason})" if reason else ""))
    return [str(s["station_id"]) for s in body if s.get("station_id") is not None]


def fetch_v1(url: str, key: str, station_id: int | str | list, *, max_pages: int = 1000) -> Iterator[str]:
    """Yield ADIF text chunks until the instance reports nothing new."""
    endpoint = f"{_base(url)}/index.php/api/get_contacts_adif"
    # Wavelog accepts a single id or a JSON array of ids
    if isinstance(station_id, (list, tuple)):
        station: int | str | list = [int(s) for s in station_id] if len(station_id) > 1 else str(station_id[0])
    else:
        station = str(station_id)
    last_id = 0
    for _ in range(max_pages):
        resp = requests.post(endpoint, json={"key": key, "station_id": station,
                                             "fetchfromid": last_id}, timeout=TIMEOUT)
        body = _json(resp, endpoint)
        if body.get("status") not in (None, "successful"):
            raise WavelogError(f"Wavelog reported failure: {body.get('reason') or body}")
        adif = body.get("adif") or ""
        new_last = int(body.get("lastfetchedid") or last_id)
        if adif.strip():
            yield adif
        if new_last <= last_id or not adif.strip():
            return
        last_id = new_last


def fetch_v2(url: str, token: str, station_id: int | str | list | None = None, *,
             per_page: int = 5000, max_pages: int = 1000) -> Iterator[str]:
    """Yield ADIF text chunks using the v2 API (bearer token). Experimental."""
    endpoint = f"{_base(url)}/index.php/api/v2/qso"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    since_id = 0
    for _ in range(max_pages):
        params = {"format": "adif", "since_id": since_id, "per_page": per_page}
        if isinstance(station_id, (list, tuple)):
            if station_id:
                params["station_id"] = ",".join(str(s) for s in station_id)
        elif station_id not in (None, ""):
            params["station_id"] = station_id
        resp = requests.get(endpoint, params=params, headers=headers, timeout=TIMEOUT)
        body = _json(resp, endpoint)
        data = body.get("data") or {}
        meta = body.get("meta") or {}
        adif = data.get("adif") or ""
        new_last = int(data.get("lastfetchedid") or since_id)
        if adif.strip():
            yield adif
        if not adif.strip() or new_last <= since_id or meta.get("has_more") is False:
            return
        since_id = new_last
