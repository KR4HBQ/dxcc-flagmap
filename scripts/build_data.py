#!/usr/bin/env python3
"""Regenerate the bundled data files in src/dxcc_flagmap/data/.

This is a maintainer script - end users never need to run it.

Inputs (downloaded by hand or by CI):
  --dxcc-json   K0SWE dxcc.json  https://github.com/k0swe/dxcc-json
  --ne-dir      directory containing Natural Earth GeoJSON files
                (ne_50m_admin_0_countries, ne_50m_admin_0_map_units,
                 ne_110m_land) from nvkelso/natural-earth-vector
  --flags-dir   flag-icons package directory (npm: flag-icons), uses flags/4x3/*.svg

Outputs:
  data/dxcc_entities.json   [{dxcc, name, iso, lat, lon, continent, prefix}, ...]
  data/land.json            simplified land polygons for the world map
  data/flags/<iso>.png      40x30 flag PNGs (needs `pip install cairosvg`)

Entity coordinates are approximate label points derived from Natural Earth
geometry. Run scripts/apply_cty.py afterwards to replace them with AD1C
cty.dat reference points (what the shipped data uses). Entities that Natural
Earth does not model separately fall back to their parent country's point or
to the manual table in MANUAL_POINTS. PRs improving them are welcome.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Home nations that flag-icons has dedicated flags for (dxcc.json says "GB").
ISO_OVERRIDE: dict[int, str] = {223: "GB-ENG", 279: "GB-SCT", 294: "GB-WLS", 265: "GB-NIR",
                                167: "AX",    # Market Reef: the Finnish half belongs to Aland
                                246: "SMOM"}  # Sovereign Military Order of Malta, scripts/flags/smom.svg

# Flags flag-icons does not ship, drawn for this project (scripts/flags/<iso>.svg).
EXTRA_FLAGS = Path(__file__).resolve().parent / "flags"

# (lat, lon) for entities Natural Earth does not give a usable point for.
MANUAL_POINTS: dict[int, tuple[float, float]] = {
    6: (64.0, -150.0),     # Alaska
    110: (20.8, -156.3),   # Hawaii
    291: (39.0, -98.0),    # United States of America
    1: (56.0, -106.0),     # Canada
    20: (0.2, -176.5),     # Baker & Howland Islands
    24: (-54.4, 3.4),      # Bouvet Island
    117: (46.2, 6.15),     # ITU Headquarters (Geneva)
    167: (60.3, 19.1),     # Market Island
    199: (-68.8, -90.6),   # Peter I Island
    233: (36.14, -5.35),   # Gibraltar
    246: (41.9, 12.45),    # Sovereign Military Order of Malta (Rome)
    247: (10.0, 114.0),    # Spratly Islands
    289: (40.75, -73.97),  # United Nations HQ (New York)
    519: (17.5, -63.1),    # Saba & Sint Eustatius
    520: (12.2, -68.3),    # Bonaire
    # extend as gaps are found (run with --report to list them)
}


def ring_area_centroid(ring):
    a = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(ring, ring[1:]):
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    if abs(a) < 1e-12:
        xs = [p[0] for p in ring]
        ys = [p[1] for p in ring]
        return sum(xs) / len(xs), sum(ys) / len(ys), 0.0
    a *= 0.5
    return cx / (6 * a), cy / (6 * a), abs(a)


def label_point(geom):
    """Centroid of the largest polygon (lon, lat)."""
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    best = max((ring_area_centroid(p[0]) for p in polys), key=lambda t: t[2])
    return best[0], best[1]


def norm(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


def build_index(ne_dir: Path):
    by_iso: dict[str, tuple[float, float]] = {}
    by_name: dict[str, tuple[float, float]] = {}
    for fname in ("ne_50m_admin_0_countries.geojson", "ne_50m_admin_0_map_units.geojson"):
        data = json.loads((ne_dir / fname).read_text())
        for f in data["features"]:
            p = f["properties"]
            lon, lat = label_point(f["geometry"])
            iso = p.get("ISO_A2_EH") or p.get("ISO_A2")
            if iso and iso != "-99" and fname.startswith("ne_50m_admin_0_countries"):
                by_iso[iso.upper()] = (lat, lon)
            for key in ("NAME", "NAME_LONG", "ADMIN", "NAME_EN", "FORMAL_EN", "GEOUNIT", "SUBUNIT"):
                v = p.get(key)
                if v:
                    by_name.setdefault(norm(v), (lat, lon))
    return by_iso, by_name


def simplify_land(ne_dir: Path, out: Path):
    data = json.loads((ne_dir / "ne_110m_land.geojson").read_text())
    polys = []
    for f in data["features"]:
        g = f["geometry"]
        ps = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        for p in ps:
            polys.append([[round(x, 2), round(y, 2)] for x, y in p[0]])
    out.write_text(json.dumps(polys, separators=(",", ":")))
    return len(polys)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dxcc-json", required=True, type=Path)
    ap.add_argument("--ne-dir", required=True, type=Path)
    ap.add_argument("--flags-dir", required=True, type=Path)
    ap.add_argument("--out", default=Path(__file__).resolve().parents[1] / "src/dxcc_flagmap/data", type=Path)
    ap.add_argument("--report", action="store_true", help="list entities without coordinates / flags")
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "flags").mkdir(exist_ok=True)

    raw = json.loads(args.dxcc_json.read_text())["dxcc"]
    by_iso, by_name = build_index(args.ne_dir)

    entities, no_point = [], []
    for e in raw:
        if e.get("deleted"):
            continue
        code = int(e["entityCode"])
        iso = ISO_OVERRIDE.get(code) or (e.get("countryCode") or "").upper()
        pt = MANUAL_POINTS.get(code) or by_name.get(norm(e["name"])) or by_iso.get(iso)
        if pt is None:
            no_point.append((code, e["name"], iso))
            continue
        entities.append({
            "dxcc": code,
            "name": e["name"],
            "iso": iso.lower(),
            "lat": round(pt[0], 2),
            "lon": round(pt[1], 2),
            "continent": (e.get("continent") or [""])[0],
            "prefix": (e.get("prefix") or "").split(",")[0],
        })
    entities.sort(key=lambda x: x["dxcc"])
    (args.out / "dxcc_entities.json").write_text(json.dumps(entities, indent=0, separators=(",", ":")))

    n_land = simplify_land(args.ne_dir, args.out / "land.json")

    # flags
    try:
        import cairosvg  # type: ignore
    except ImportError:
        print("cairosvg missing: skipping flag PNGs", file=sys.stderr)
        cairosvg = None
    missing_flag = set()
    if cairosvg:
        isos = {e["iso"] for e in entities if e["iso"]}
        for iso in sorted(isos):
            svg = args.flags_dir / "flags" / "4x3" / f"{iso}.svg"
            if not svg.exists():
                svg = EXTRA_FLAGS / f"{iso}.svg"
            if not svg.exists():
                missing_flag.add(iso)
                continue
            cairosvg.svg2png(url=str(svg), write_to=str(args.out / "flags" / f"{iso}.png"),
                             output_width=40, output_height=30)

    print(f"entities: {len(entities)}  land polys: {n_land}  no coords: {len(no_point)}  missing flags: {sorted(missing_flag)}")
    if args.report:
        for t in no_point:
            print("no point:", t)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
