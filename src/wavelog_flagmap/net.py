"""Shared HTTP settings: every request identifies the tool (some services rate-limit generic agents)."""
from __future__ import annotations

import requests

from . import __version__

USER_AGENT = f"wavelog-flagmap/{__version__} (+https://github.com/KR4HBQ/wavelog-flagmap)"
HEADERS = {"User-Agent": USER_AGENT}
TIMEOUT = 60


class FetchError(RuntimeError):
    pass


def fetch_text(url: str) -> str:
    """GET a text document (an ADIF file published at a URL)."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise FetchError(f"could not download {url}: {type(exc).__name__}") from None
    if resp.status_code != 200:
        raise FetchError(f"HTTP {resp.status_code} from {url}")
    return resp.content.decode("utf-8", errors="replace")
