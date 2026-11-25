#!/usr/bin/env python3
"""Write a minimal index.html next to the rendered PNGs (used by the Pages workflow).

    python scripts/site_index.py <dir> [CALLSIGN]
"""
from __future__ import annotations

import html
import sys
from pathlib import Path


def main() -> int:
    out = Path(sys.argv[1])
    call = html.escape(sys.argv[2] if len(sys.argv) > 2 else "")
    title = f"{call} Worked DXCC".strip()
    (out / "index.html").write_text(f"""<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>body{{font-family:sans-serif;max-width:1000px;margin:2em auto;padding:0 1em}}
img{{max-width:100%;height:auto;display:block;margin:1em 0}}</style>
<h1>{title}</h1>
<img src="dxcc-grid.png" alt="{title} - flag grid">
<img src="dxcc-map.png" alt="{title} - world map">
<p><a href="dxcc-stats.json">dxcc-stats.json</a> &middot; made with
<a href="https://github.com/KR4HBQ/wavelog-flagmap">wavelog-flagmap</a></p>
""", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
