"""Command line entry point: ``wavelog-flagmap``."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__, config as cfgmod, wavelog
from .adif import parse_adif
from .render import GridOptions, MapOptions, render_grid, render_map
from .stats import CONFIRM_FIELDS, METRICS, count_entities, ranked, summary


def _atomic_save(img, path: Path) -> None:
    tmp = path.with_suffix(".tmp.png")
    img.save(tmp, optimize=True)
    os.replace(tmp, path)  # a web server never sees a half-written file


def _load_qsos(cfg: cfgmod.Config) -> list[dict[str, str]]:
    if cfg.adif:
        return list(parse_adif(Path(cfg.adif).read_text(encoding="utf-8", errors="replace")))
    if cfg.wavelog_url and cfg.wavelog_key:
        fetch = wavelog.fetch_v2 if cfg.wavelog_api == "v2" else wavelog.fetch_v1
        stations = cfg.station_ids
        if cfg.wavelog_api != "v2" and not stations:
            stations = wavelog.station_ids_v1(cfg.wavelog_url, cfg.wavelog_key)
            if not stations:
                raise SystemExit("error: the API key's user has no station locations")
        qsos: list[dict[str, str]] = []
        for chunk in fetch(cfg.wavelog_url, cfg.wavelog_key, stations):
            qsos.extend(parse_adif(chunk))
        return qsos
    raise SystemExit("error: configure either source.adif or wavelog.url + wavelog.key "
                     "(or pass --adif FILE)")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wavelog-flagmap",
                                description="Render a Flag Counter-style worked-DXCC grid and world map from Wavelog.")
    p.add_argument("-c", "--config", help="YAML config file")
    p.add_argument("--adif", help="use a local ADIF file instead of the Wavelog API")
    p.add_argument("--url", help="Wavelog base URL (overrides wavelog.url)")
    p.add_argument("--station-id", help="Station Location id(s), e.g. 1, 1,3, 1-12 or all (default: all)")
    p.add_argument("--api", choices=("v1", "v2"), help="Wavelog API version (default v1)")
    p.add_argument("-o", "--output-dir", help="where to write the images (default ./out)")
    p.add_argument("--callsign", help="callsign shown in the titles")
    p.add_argument("--metric", choices=METRICS, help="count QSOs or confirmed QSOs per entity")
    p.add_argument("--confirmed-by", metavar="SOURCES",
                   help=f"confirmation sources that count, comma separated ({','.join(CONFIRM_FIELDS)}); "
                        "default lotw,qsl")
    p.add_argument("--theme", choices=("light", "dark"))
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = cfgmod.load(args.config)
    if args.adif:
        cfg.adif = args.adif
    if args.url:
        cfg.wavelog_url = args.url
    if args.station_id:
        cfg.station_ids = cfgmod.parse_station_ids(args.station_id)
    if args.api:
        cfg.wavelog_api = args.api
    if not cfg.wavelog_key:
        cfg.wavelog_key = os.environ.get("WAVELOG_API_KEY")
    if args.output_dir:
        cfg.output_dir = args.output_dir
    if args.callsign:
        cfg.callsign = args.callsign
    if args.metric:
        cfg.metric = args.metric
    if args.confirmed_by:
        cfg.confirmed_by = cfgmod._list(args.confirmed_by)
    if args.theme:
        cfg.theme = args.theme

    qsos = _load_qsos(cfg)
    try:
        counts, skipped = count_entities(qsos, cfg.confirmed_by)
    except ValueError as exc:
        raise SystemExit(f"error: {exc}")
    rows = ranked(counts, cfg.metric)
    if not rows:
        print("no entities found - nothing to render", file=sys.stderr)
        return 1

    out = Path(cfg.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    call = cfg.callsign
    gopt = GridOptions(title=cfg.grid.pop("title", f"{call} Worked DXCC".strip()),
                       metric=cfg.metric, theme=cfg.theme, footer_text=summary(counts), **cfg.grid)
    mopt = MapOptions(title=cfg.map.pop("title", ""), theme=cfg.theme, footer_text=summary(counts), **cfg.map)
    _atomic_save(render_grid(rows, gopt), out / "dxcc-grid.png")
    _atomic_save(render_map(rows, mopt), out / "dxcc-map.png")
    (out / "dxcc-stats.json").write_text(json.dumps({
        "callsign": call, "metric": cfg.metric, "confirmed_by": cfg.confirmed_by,
        "worked": len(counts), "confirmed": sum(1 for c in counts.values() if c.confirmed), "qsos": len(qsos), "skipped_no_entity": skipped,
        "entities": [{"dxcc": r.entity.dxcc, "name": r.entity.name, "qsos": r.qsos,
                      "confirmed": r.confirmed} for r in rows],
    }, indent=1))
    print(f"wrote {out}/dxcc-grid.png, dxcc-map.png, dxcc-stats.json "
          f"({summary(counts)}; {skipped} QSOs without a DXCC entity skipped)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
