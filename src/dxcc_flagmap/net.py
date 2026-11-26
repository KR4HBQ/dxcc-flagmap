"""Shared HTTP settings: every request identifies the tool (some services rate-limit generic agents)."""
from __future__ import annotations

from urllib.parse import urlsplit

import requests

from . import __version__

USER_AGENT = f"dxcc-flagmap/{__version__} (+https://github.com/KR4HBQ/dxcc-flagmap)"
HEADERS = {"User-Agent": USER_AGENT}
TIMEOUT = 60


class FetchError(RuntimeError):
    pass


def redact(url: str) -> str:
    """scheme://host/path of a URL: share links and signed URLs carry access tokens in the query."""
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc.rpartition('@')[2]}{p.path}" + ("?..." if p.query else "")


def fetch_text(url: str) -> str:
    """GET a text document (an ADIF file published at a URL)."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise FetchError(f"could not download {redact(url)}: {type(exc).__name__}") from None
    if resp.status_code != 200:
        raise FetchError(f"HTTP {resp.status_code} from {redact(url)}")
    return resp.content.decode("utf-8", errors="replace")
