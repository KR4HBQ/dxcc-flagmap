"""Command line entry point: ``dxcc-flagmap``."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__, clublog, config as cfgmod, lotw, net, qrz, wavelog, wrl
from .adif import parse_adif
from .render import MAP_VIEWS, GridOptions, MapOptions, render_grid, render_map
from .stats import CONFIRM_FIELDS, METRICS, count_entities, ranked, summary


def _atomic_save(img, path: Path) -> None:
    tmp = path.with_suffix(".tmp.png")
    img.save(tmp, optimize=True)
    os.replace(tmp, path)  # a web server never sees a half-written file


SOURCES = ("wavelog", "lotw", "clublog", "qrz", "wrl", "adif")


def _source(cfg: cfgmod.Config) -> str | None:
    if cfg.source:
        return cfg.source
    if cfg.adif:
        return "adif"
    if cfg.wavelog_url:
        return "wavelog"
    if cfg.lotw_username:
        return "lotw"
    if cfg.clublog_token:
        return "clublog"
    if cfg.qrz_key:
        return "qrz"
    if cfg.wrl_key:
        return "wrl"
    return None


def _load_qsos(cfg: cfgmod.Config) -> list[dict[str, str]]:
    source = _source(cfg)
    if source == "adif":
        if not cfg.adif:
            raise SystemExit("error: source adif needs an ADIF file or URL (--adif)")
        if cfg.adif.lower().startswith(("http://", "https://")):
            try:
                text = net.fetch_text(cfg.adif)
            except net.FetchError as exc:
                raise SystemExit(f"error: {exc}")
        else:
            text = Path(cfg.adif).read_text(encoding="utf-8", errors="replace")
        return list(parse_adif(text))
    if source == "lotw":
        if not (cfg.lotw_username and cfg.lotw_password):
            raise SystemExit("error: LoTW needs LOTW_USERNAME and LOTW_PASSWORD (environment variables)")
        try:
            text = lotw.fetch(cfg.lotw_username, cfg.lotw_password, owncall=cfg.lotw_owncall)
        except lotw.LotwError as exc:
            raise SystemExit(f"error: {exc}")
        return [lotw.normalize(r) for r in parse_adif(text)]
    if source == "clublog":
        call = cfg.clublog_callsign or cfg.callsign
        if not (cfg.clublog_token and call):
            raise SystemExit("error: Club Log needs CLUBLOG_TOKEN (environment variable) and a callsign "
                             "(--callsign or CLUBLOG_CALLSIGN)")
        try:
            text = clublog.fetch(call, cfg.clublog_token)
        except clublog.ClublogError as exc:
            raise SystemExit(f"error: {exc}")
        return list(parse_adif(text))
    if source == "qrz":
        if not cfg.qrz_key:
            raise SystemExit("error: the QRZ Logbook needs QRZ_LOGBOOK_KEY (environment variable)")
        try:
            return [qrz.normalize(r) for chunk in qrz.fetch(cfg.qrz_key) for r in parse_adif(chunk)]
        except qrz.QrzError as exc:
            raise SystemExit(f"error: {exc}")
    if source == "wrl":
        if not cfg.wrl_key:
            raise SystemExit("error: World Radio League needs WRL_API_KEY (environment variable)")
        try:
            return list(wrl.fetch(cfg.wrl_key))
        except wrl.WrlError as exc:
            raise SystemExit(f"error: {exc}")
    if source == "wavelog" and cfg.wavelog_url and cfg.wavelog_key:
        try:
            return _load_wavelog(cfg)
        except wavelog.WavelogError as exc:
            raise SystemExit(f"error: {exc}")
    if source == "wavelog":
        raise SystemExit("error: Wavelog needs wavelog.url and the WAVELOG_API_KEY environment variable")
    raise SystemExit("error: no data source: pass --adif FILE_OR_URL, --url WAVELOG_URL or --source "
                     "lotw/clublog/qrz/wrl "
                     "(or set them in the config file)")


def _load_wavelog(cfg: cfgmod.Config) -> list[dict[str, str]]:
    wavelog.check_url(cfg.wavelog_url, allow_http=cfg.wavelog_allow_http)
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


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dxcc-flagmap",
                                description="Render a Flag Counter-style worked-DXCC grid and world map from Wavelog, LoTW, Club Log, "
                                            "QRZ Logbook, World Radio League or ADIF.")
    p.add_argument("-c", "--config", help="YAML config file")
    p.add_argument("--source", choices=SOURCES,
                   help="where the QSOs come from (default: the first configured of adif, wavelog, lotw, clublog, qrz, wrl; "
                        "credentials come from WAVELOG_API_KEY, LOTW_USERNAME/LOTW_PASSWORD, CLUBLOG_TOKEN, "
                        "QRZ_LOGBOOK_KEY, WRL_API_KEY)")
    p.add_argument("--adif", metavar="FILE_OR_URL", help="read an ADIF file (local path or http(s) URL)")
    p.add_argument("--lotw-owncall", metavar="CALL",
                   help="LoTW: only QSOs made as this callsign (credentials: LOTW_USERNAME / LOTW_PASSWORD)")
    p.add_argument("--url", help="Wavelog base URL (overrides wavelog.url)")
    p.add_argument("--station-id", help="Station Location id(s), e.g. 1, 1,3, 1-12 or all (default: all)")
    p.add_argument("--api", choices=("v1", "v2"), help="Wavelog API version (default v1)")
    p.add_argument("--allow-http", action="store_true",
                   help="allow a plain http:// Wavelog URL (sends the API key unencrypted; localhost is always allowed)")
    p.add_argument("-o", "--output-dir", help="where to write the images (default ./out)")
    p.add_argument("--callsign", help="callsign shown in the titles")
    p.add_argument("--metric", choices=METRICS, help="count QSOs or confirmed QSOs per entity")
    p.add_argument("--confirmed-by", metavar="SOURCES",
                   help=f"confirmation sources that count, comma separated ({','.join(CONFIRM_FIELDS)}); "
                        "default lotw,qsl")
    p.add_argument("--map-view", choices=tuple(MAP_VIEWS),
                   help="cropped (default: no polar strips, bigger flags) or full (84N to 58S)")
    p.add_argument("--grid-labels", choices=("prefix", "none"), help="text under each grid count")
    p.add_argument("--theme", choices=("light", "dark"))
    p.add_argument("--no-credit", action="store_true",
                   help='leave out the "Get your own: github.com/..." line in the footers')
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = cfgmod.load(args.config)
    if args.source:
        cfg.source = args.source
    if args.adif:
        cfg.adif = args.adif
    if args.lotw_owncall:
        cfg.lotw_owncall = args.lotw_owncall
    if args.url:
        cfg.wavelog_url = args.url
    if args.station_id:
        cfg.station_ids = cfgmod.parse_station_ids(args.station_id)
    if args.api:
        cfg.wavelog_api = args.api
    if args.allow_http:
        cfg.wavelog_allow_http = True
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
    if args.map_view:
        cfg.map["view"] = args.map_view
    if args.grid_labels:
        cfg.grid["labels"] = args.grid_labels
    if args.theme:
        cfg.theme = args.theme
    if args.no_credit:
        cfg.grid["credit"] = cfg.map["credit"] = False

    confirmations = _source(cfg) != "wrl"  # WRL contacts carry no QSL status
    if not confirmations and cfg.metric == "confirmed":
        raise SystemExit("error: World Radio League has no confirmation data; use --metric qsos")
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
    foot = summary(counts, confirmations=confirmations)
    gopt = GridOptions(title=cfg.grid.pop("title", f"{call} Worked DXCC".strip()),
                       metric=cfg.metric, theme=cfg.theme, footer_text=foot, **cfg.grid)
    mopt = MapOptions(title=cfg.map.pop("title", ""), theme=cfg.theme, footer_text=foot, **cfg.map)
    _atomic_save(render_grid(rows, gopt), out / "dxcc-grid.png")
    _atomic_save(render_map(rows, mopt), out / "dxcc-map.png")
    (out / "dxcc-stats.json").write_text(json.dumps({
        "callsign": call, "metric": cfg.metric, "confirmed_by": cfg.confirmed_by,
        "worked": len(counts), "confirmed": sum(1 for c in counts.values() if c.confirmed), "qsos": len(qsos), "skipped_no_entity": skipped,
        "entities": [{"dxcc": r.entity.dxcc, "name": r.entity.name, "qsos": r.qsos,
                      "confirmed": r.confirmed} for r in rows],
    }, indent=1))
    print(f"wrote {out}/dxcc-grid.png, dxcc-map.png, dxcc-stats.json "
          f"({foot}; {skipped} QSOs without a DXCC entity skipped)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
