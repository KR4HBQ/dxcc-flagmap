#!/usr/bin/env python3
"""Replace entity coordinates in data/dxcc_entities.json with AD1C cty.dat reference points.

Maintainer script, run after build_data.py:

    curl -o cty.dat https://www.country-files.com/cty/cty.dat
    python scripts/apply_cty.py cty.dat [--report]

cty.dat itself is NOT bundled; only each entity's latitude/longitude and primary prefix
(shown under each flag in the grid) are copied.
Records are matched by ALIASES prefix, normalized name, then prefix.
WAE-only entries (prefix starting with '*') are ignored. cty.dat longitudes are
positive WEST, so they are negated here. Entities that do not match keep their
Natural Earth / manual coordinates; --report lists them.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "src" / "dxcc_flagmap" / "data"
DATA = DATA_DIR / "dxcc_entities.json"
PREFIXES = DATA_DIR / "prefixes.json"

# WAE-only cty.dat records (prefix starting with '*') belong to these DXCC entities.
WAE_PARENT = {"4U1V": 206, "GM/S": 279, "IG9": 248, "IT9": 248, "JW/B": 259, "TA1": 390}
_MODIFIERS = re.compile(r"[(\[<{~].*$")

# DXCC number -> cty.dat primary prefix, where names and prefixes disagree.
ALIASES: dict[int, str] = {
    24: "3Y/B", 199: "3Y/P", 111: "VK0H", 117: "4U1I", 289: "4U1U", 125: "CE0Z", 217: "CE0X",
    192: "JD/O", 204: "XF4", 216: "HK0/A", 253: "PY0S", 273: "PY0T", 230: "DL", 414: "9Q",
    10: "FT/Z", 41: "FT/W", 124: "FT/J",
}


# Keep the build_data.py point: cty.dat uses a population point (Canada: southern Ontario)
# or the pole (Antarctica), which looks wrong on a world map.
KEEP = {1, 13}


def norm(s: str) -> str:
    s = s.lower().replace("&", "and").replace("st.", "saint").replace("st ", "saint ")
    return re.sub(r"[^a-z0-9]", "", s)


def parse_cty(text: str, *, include_wae: bool = False) -> list[dict]:
    """Records: name, prefix, continent, lat, lon (east positive), wae, aliases (raw strings)."""
    out = []
    for rec in text.split(";"):
        head, _, body = rec.strip().partition("\n")
        parts = [p.strip() for p in head.split(":")]
        if len(parts) < 8 or not parts[0]:
            continue
        name, _cq, _itu, cont, lat, lon, _tz, prefix = parts[:8]
        wae = prefix.startswith("*")
        if wae and not include_wae:
            continue  # WAE / CQ-only entity, not DXCC
        aliases = [a.strip() for a in body.replace("\n", "").split(",") if a.strip()]
        out.append({"name": name, "prefix": prefix.lstrip("*").upper(), "continent": cont,
                    "lat": float(lat), "lon": -float(lon), "wae": wae, "aliases": aliases})
    return out


def prefix_table(records: list[dict], dxcc_of: dict[str, int]) -> dict[str, dict[str, int]]:
    """{"p": {prefix: dxcc}, "c": {exact callsign: dxcc}} from the cty.dat alias lists."""
    table: dict[str, dict[str, int]] = {"p": {}, "c": {}}
    for r in records:
        code = WAE_PARENT.get(r["prefix"]) if r["wae"] else dxcc_of.get(r["prefix"])
        if code is None:
            print(f"  no DXCC entity for cty.dat record {r['prefix']} {r['name']}")
            continue
        for alias in r["aliases"]:
            a = _MODIFIERS.sub("", alias).upper()
            if a.startswith("="):
                table["c"][a[1:]] = code
            elif a:
                table["p"][a] = code
    return table


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cty")
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()

    cty = parse_cty(Path(args.cty).read_text(encoding="latin-1"))
    by_prefix = {c["prefix"]: c for c in cty}
    by_name = {norm(c["name"]): c for c in cty}

    rows = json.loads(DATA.read_text(encoding="utf-8"))
    dxcc_of: dict[str, int] = {}  # cty.dat primary prefix -> DXCC number
    hit = miss = 0
    unmatched = []
    for r in rows:
        c = (by_prefix.get(ALIASES.get(r["dxcc"], "")) or by_name.get(norm(r["name"]))
             or by_prefix.get(r["prefix"].upper()))
        if c is None:
            miss += 1
            unmatched.append(f'{r["dxcc"]:>4} {r["prefix"]:<6} {r["name"]}')
            continue
        if c["prefix"] in dxcc_of:
            print(f'  cty.dat record {c["prefix"]} matched twice: DXCC {dxcc_of[c["prefix"]]} and {r["dxcc"]}')
        dxcc_of[c["prefix"]] = r["dxcc"]
        if r["dxcc"] not in KEEP:
            r["lat"], r["lon"] = round(c["lat"], 2), round(c["lon"], 2)
        r["prefix"] = c["prefix"].split("/")[0]  # the familiar prefix (VE, not VA); "3Y/B" -> "3Y"
        hit += 1
    DATA.write_text(json.dumps(rows, indent=0, separators=(",", ":")))  # same format as build_data.py
    table = prefix_table(parse_cty(Path(args.cty).read_text(encoding="latin-1"), include_wae=True), dxcc_of)
    PREFIXES.write_text(json.dumps(table, sort_keys=True, separators=(",", ":")))
    print(f"cty.dat records: {len(cty)}  entities updated: {hit}  unmatched: {miss}  "
          f"prefixes: {len(table['p'])}  exact calls: {len(table['c'])}")
    if args.report:
        print("\n".join(unmatched))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
